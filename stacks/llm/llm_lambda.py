from typing import Any

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import (
    aws_ecr_assets as ecr_assets,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as targets,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct


class LLMLambdaFunctionsStack(Stack):
    """Creates the Lambda functions for LLM processing of email content.

    This stack sets up the Lambda functions that process email content using LLM models
    via AWS Bedrock. It creates:

    1. IAM role with permissions for Lambda, S3, Athena, Glue, and Bedrock
    2. Docker-based Lambda function for LLM processing
    3. CloudWatch log group for Lambda logs
    4. EventBridge rule to trigger Lambda on new query data

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        llm_region (str): The AWS region for LLM services
        athena_database (str): The name of the Athena database
        athena_queries_bucket (str): The name of the S3 bucket for Athena queries
        athena_bucket (s3.IBucket): The S3 bucket for Athena data
        llm_image_asset (ecr_assets.DockerImageAsset): The Docker image asset for the Lambda function
        queries_table_name (str): The name of the Athena table for email queries
        responses_table_name (str): The name of the Athena table for LLM responses
        kb_id (str): The ID of the knowledge base to use for LLM processing
        phase (str): Deployment phase (e.g., "dev", "prod")
        project (str): The project name used for resource naming and tagging
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        llmresponse_lambda_function: The Lambda function for LLM processing

    Output:
        {project}-LLMResponderRuleBucket: The name of the S3 bucket that triggers the EventBridge rule
        {project}-LLMResponderRuleKeyPrefix: The key prefix that triggers the EventBridge rule
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        llm_region: str,
        athena_database: str,
        athena_queries_bucket: str,
        athena_bucket: s3.IBucket,
        llm_image_asset: ecr_assets.DockerImageAsset,
        queries_table_name: str,
        responses_table_name: str,
        kb_id: str,
        phase: str,
        project: str,
        **kwargs: Any,
    ) -> None:
        description = "Stack containing Lambda functions for processing EZComms data"
        super().__init__(scope, id, description=description, **kwargs)

        # Tag the stack resources for cost allocation and management
        phase_tag = phase.capitalize()
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", f"{project}-Functions")

        # Take the data_env region as the core region where the lambda function sits and where knowledge base will be found
        kb_region = self.region

        # Need to create an IAM role for the LLM lambda function for cross-environment compatibility
        lambda_role = iam.Role(
            self,
            f"{project}-LLMResponseLambdaRole",
            role_name=f"{project}-LLMResponseLambdaRole-{phase}-{kb_region}",  # Need to specify the region for a role otherwise get an error
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        Tags.of(lambda_role).add("ResourceType", "Role")
        Tags.of(lambda_role).add("Service", "IAM")

        # Set up lambda functions
        ### LLM Response Lambda
        llmresponse_lambda_function = _lambda.DockerImageFunction(
            self,
            f"{project}-LLMResponseLambda",
            function_name=f"{project}-LLMResponseLambda",
            code=_lambda.DockerImageCode.from_ecr(
                llm_image_asset.repository,
                tag=llm_image_asset.image_tag,
            ),
            environment={
                "LLM_REGION": llm_region,
                "KB_REGION": kb_region,
                "DATA_REGION": kb_region,
                "KB_ID": kb_id,
                "ATHENA_OUTPUT_BUCKET": athena_bucket.bucket_name,
                "ATHENA_DATABASE": athena_database,
                "ATHENA_QUERIES_TABLE": queries_table_name,
                "ATHENA_RESPONSES_TABLE": responses_table_name,
                "ATHENA_QUERIES_BUCKET": athena_queries_bucket,
                "PROJECT": project,
            },
            memory_size=1024,
            timeout=Duration.minutes(5),
            role=lambda_role,  # Tie lambda to cross-region role
        )
        Tags.of(llmresponse_lambda_function).add("ResourceType", "Function")
        Tags.of(llmresponse_lambda_function).add("Service", "Lambda")

        # Cloudwatch logs retention definition for snapshot lambda
        responder_log_group = logs.LogGroup(
            self,
            f"{project}-LLMLambdaLogGroup",
            log_group_name=f"/aws/lambda/{llmresponse_lambda_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        Tags.of(responder_log_group).add("ResourceType", "LogGroup")
        Tags.of(responder_log_group).add("Service", "CloudWatch")

        # Set up permissions for LLM lambda - do explicitly as adds the permissions directly to
        # the role's policy, rather than creating a bucket policy that references the role which could become
        # circular
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                    "s3:DeleteObject",
                ],
                resources=[
                    f"arn:aws:s3:::{athena_bucket.bucket_name}",
                    f"arn:aws:s3:::{athena_bucket.bucket_name}/*",
                ],
            )
        )
        # Since athena-queries bucket isn't set up in storage stack (but already exists), can use the grant_read_write instead.
        athena_queries_bucket = s3.Bucket.from_bucket_name(
            self, "AthenaQueriesBucket", athena_queries_bucket
        )
        athena_queries_bucket.grant_read_write(lambda_role)
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    # Existing permissions
                    "glue:GetTable",
                    "glue:GetPartitions",
                    "glue:GetDatabase",
                    "glue:CreateTable",
                    "glue:UpdateTable",
                    # Additional permissions for AWS Wrangler
                    "glue:BatchCreatePartition",
                    "glue:BatchDeletePartition",
                    "glue:BatchGetPartition",
                    "glue:CreatePartition",
                    "glue:DeletePartition",
                    "glue:GetPartition",
                    "glue:UpdatePartition",
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:GetWorkGroup",
                    "athena:BatchGetQueryExecution",
                    "athena:ListQueryExecutions",
                    "athena:StopQueryExecution",
                    "athena:GetDataCatalog",
                ],
                resources=["*"],
            )
        )

        # Need to define both the models we're allowed to invoke...
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:GetModelCustomizationJob",
                    "bedrock:ListModelCustomizationJobs",
                    "bedrock:GetFoundationModel",
                ],
                resources=[
                    "*"
                    # Claude 3.5 Haiku model ARNs (both formats)
                    # f"arn:aws:bedrock:{llm_region}::foundation-model/us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    # f"arn:aws:bedrock:{llm_region}::{self.account}:inference-profile/us.anthropic.claude-3-5-haiku-20241022-v1:0",
                    # Claude 3.5 Sonnet model ARNs (both formats)
                    # f"arn:aws:bedrock:{llm_region}::foundation-model/us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                    # f"arn:aws:bedrock:{llm_region}::{self.account}:inference-profile/us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                ],
            )
        )

        # ...and also which knowledge base the functions can connect to.
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:GetKnowledgeBase",
                    "bedrock:RetrieveFromKnowledgeBase",
                    "bedrock:ListKnowledgeBases",
                    "bedrock:Retrieve",
                ],
                resources=[
                    # Give access to just specific knowledge base - least privilege principle
                    # f"arn:aws:bedrock:{kb_region}:{self.account}:knowledge-base/{kb_id}",
                    "*"
                ],
            )
        )

        # Create CloudWatch Event Rule to trigger upon parquet file being added to the table S3 area
        llmresponder_rule = events.Rule(
            self,
            f"{project}-LLMResponderRule",
            description="Trigger on new query upload with inbuilt delay of 15 seconds",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [athena_bucket.bucket_name]},
                    "object": {"key": [{"prefix": f"{queries_table_name}/"}]},
                },
            ),
        )

        llmresponder_rule.add_target(
            targets.LambdaFunction(llmresponse_lambda_function)
        )

        # Store the Lambda function as a property so it can be accessed from outside
        self.llmresponse_lambda_function = llmresponse_lambda_function

        # Checks
        CfnOutput(
            self,
            f"{project}-LLMResponderRuleBucket",
            value=athena_bucket.bucket_name,
            description="Athena bucket that triggers the EventBridge rule",
        )

        CfnOutput(
            self,
            f"{project}-LLMResponderRuleKeyPrefix",
            value=f"{queries_table_name}/*",
            description="Key prefix within the Athena bucket that triggers the EventBridge rule",
        )
