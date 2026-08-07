from typing import Any, Optional

from aws_cdk import Duration, RemovalPolicy, Stack, Tags
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


class OutgoingLambdaFunctionsStack(Stack):
    """Creates the Lambda functions for sending email responses.

    This stack sets up the Lambda functions that send automated email responses using
    Amazon SES. It creates:

    1. Docker-based Lambda function for email sending
    2. CloudWatch log group for Lambda logs
    3. IAM permissions for S3 access and SES sending
    4. EventBridge rule to trigger Lambda on new response data

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        athena_database (str): The name of the Athena database
        athena_bucket (s3.IBucket): The S3 bucket for Athena data
        sender_lambda_image_asset (ecr_assets.DockerImageAsset): The Docker image asset for the Lambda function
        responses_table_name (str): The name of the table containing LLM responses
        domain_name (str): The domain name for email sending
        email_subject (str): The subject line for outgoing emails
        sender_email_address (str): The sender email address
        followup_email_address (str): The email address for follow-up inquiries
        sender_mode (str): Email sending mode - 'ses' or 'notify'
        api_key_name (Optional[str]): Name of the Notify API key in Secrets Manager (required for notify mode)
        api_key_arn (Optional[str]): ARN of the Notify API key secret (required for notify mode)
        notify_template_id (Optional[str]): GOV.UK Notify template ID (required for notify mode)
        phase (str): Deployment phase (e.g., "dev", "prod")
        project (str): The project name used for resource naming and tagging
        **kwargs: Additional arguments passed to the Stack constructor
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        athena_database: str,
        athena_bucket: s3.IBucket,
        sender_lambda_image_asset: ecr_assets.DockerImageAsset,
        responses_table_name: str,
        domain_name: str,
        email_subject: str,
        sender_email_address: str,
        followup_email_address: str,
        phase: str,
        project: str,
        sender_mode: str,
        api_key_name: Optional[str] = None,
        api_key_arn: Optional[str] = None,
        notify_template_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        description = (
            "Stack containing Lambda functions for sending EZComms email responses"
        )
        super().__init__(scope, id, description=description, **kwargs)

        # Validate sender_mode and required parameters
        sender_mode = sender_mode.lower()
        if sender_mode not in ["ses", "notify"]:
            raise ValueError(
                f"Invalid sender_mode: {sender_mode}. Must be 'ses' or 'notify'"
            )

        if sender_mode == "notify":
            if not all([api_key_name, api_key_arn, notify_template_id]):
                raise ValueError(
                    "Notify mode requires api_key_name, api_key_arn, and notify_template_id"
                )

        # Tag the stack resources for cost allocation and management
        phase_tag = phase.capitalize()
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", f"{project}-EmailSenderFunctions")

        ### Lambda function to send emails

        # dependencies_layer=PythonLayerVersion(
        #     self, "EmailSenderDependencies",
        #     entry="./layers/email_handler/",
        #     compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
        # )

        lambda_environment = {
            "ATHENA_OUTPUT_BUCKET": athena_bucket.bucket_name,
            "ATHENA_DATABASE": athena_database,
            "ATHENA_RESPONSES_TABLE": responses_table_name,
            "FOLLOWUP_EMAIL_ADDRESS": followup_email_address,
            "SENDER_MODE": sender_mode,
        }

        # Add mode-specific environment variables
        if sender_mode == "ses":
            lambda_environment.update(
                {
                    "EMAIL_SUBJECT": email_subject,
                    "SENDER_EMAIL_ADDRESS": sender_email_address,
                }
            )
        else:  # notify mode
            lambda_environment.update(
                {
                    "API_KEY_NAME": api_key_name,
                    "SECRET_REGION": self.region,
                    "NOTIFY_TEMPLATE_ID": notify_template_id,
                }
            )

        emailsender_lambda_function = _lambda.DockerImageFunction(
            self,
            f"{project}-EmailSenderLambda",
            function_name=f"{project}-EmailSenderLambda",
            code=_lambda.DockerImageCode.from_ecr(
                sender_lambda_image_asset.repository,
                tag=sender_lambda_image_asset.image_tag,
            ),
            environment=lambda_environment,
            memory_size=1024,
            timeout=Duration.minutes(5),
        )
        Tags.of(emailsender_lambda_function).add("ResourceType", "Function")
        Tags.of(emailsender_lambda_function).add("Service", "Lambda")

        # Cloudwatch logs retention definition for email sender lambda
        emailsender_log_group = logs.LogGroup(
            self,
            f"{project}-EmailSenderLambdaLogGroup",
            log_group_name=f"/aws/lambda/{emailsender_lambda_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        Tags.of(emailsender_log_group).add("ResourceType", "LogGroup")
        Tags.of(emailsender_log_group).add("Service", "CloudWatch")

        # Grant permissions - for imported buckets, add policy statements directly
        emailsender_lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[
                    f"arn:aws:s3:::{athena_bucket.bucket_name}",
                    f"arn:aws:s3:::{athena_bucket.bucket_name}/*",
                ],
            )
        )

        # Add mode-specific IAM permissions
        if sender_mode == "ses":
            # Add SES permission to lambda role to send emails
            emailsender_lambda_function.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["ses:SendEmail", "ses:SendRawEmail"],
                    resources=[
                        f"arn:aws:ses:{self.region}:{self.account}:identity/{domain_name}",  # tie it to the current domain name
                    ],
                )
            )
        else:  # notify mode
            # Add Secrets Manager access to lambda role
            emailsender_lambda_function.add_to_role_policy(
                iam.PolicyStatement(
                    sid="ReadNotifySecret",
                    actions=["secretsmanager:GetSecretValue"],
                    resources=[api_key_arn],
                    effect=iam.Effect.ALLOW,
                )
            )

        # Create EventBridge rule for S3 object creation in the aicommunity_responses_dev folder
        s3_event_rule = events.Rule(
            self,
            f"{project}-S3ObjectCreatedRule",
            description=f"Trigger for fetching the user question and llm response for {project}",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [athena_bucket.bucket_name]},
                    "object": {"key": [{"prefix": f"{responses_table_name}/"}]},
                },
            ),
        )

        # Add the Lambda function as a target for the EventBridge rule
        s3_event_rule.add_target(
            targets.LambdaFunction(emailsender_lambda_function, retry_attempts=2)
        )
        emailsender_lambda_function.add_permission(
            f"{project}-EventBridgeInvokePermission",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            source_arn=s3_event_rule.rule_arn,
            action="lambda:InvokeFunction",
        )
