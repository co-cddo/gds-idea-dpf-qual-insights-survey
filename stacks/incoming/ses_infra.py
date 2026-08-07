from typing import Any
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
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
from aws_cdk import aws_route53 as route53
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_ses as ses,
)
from aws_cdk import (
    aws_ses_actions as actions,
)
from aws_cdk import (
    aws_sns as sns,
)
from constructs import Construct


def create_s3_policy(
    bucket_arn: str, account_id: str, region: str
) -> iam.PolicyStatement:
    return iam.PolicyStatement(
        actions=["s3:PutObject"],
        resources=[f"{bucket_arn}/*"],
        conditions={
            "StringEquals": {
                "AWS:SourceAccount": account_id,
                "AWS:SourceArn": f"arn:aws:ses:{region}:{account_id}:receipt-rule-set/*:receipt-rule/*",
            }
        },
    )


def create_sns_policy(
    topic_arn: str, account_id: str, region: str
) -> iam.PolicyStatement:
    return iam.PolicyStatement(
        actions=["sns:Publish"],
        resources=[topic_arn],
        conditions={
            "StringEquals": {
                "AWS:SourceAccount": account_id,
                "AWS:SourceArn": f"arn:aws:ses:{region}:{account_id}:receipt-rule-set/*:receipt-rule/*",
            }
        },
    )


class SESEmailsStack(Stack):
    """Creates the SES infrastructure for secure email ingestion and processing.

    This stack sets up the necessary components for receiving and processing emails:

    1. IAM role for SES with permissions to write to S3 and publish to SNS
    2. Optional Route53 configuration for domain verification and MX records
    3. Optional SES receipt rule set for email handling
    4. Lambda function for processing incoming emails
    5. EventBridge rule to trigger Lambda on S3 email storage

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        project (str): The project name used for resource naming and tagging
        phase (str): Deployment phase (e.g., "dev", "prod")
        email_bucket (s3.IBucket): The S3 bucket for storing raw emails
        notification_topic (sns.ITopic): The SNS topic for email notifications
        domain_name (str): The domain name for email sending/receiving
        domain_reference (str): The domain reference for MAIL FROM configuration
        athena_bucket_name_data (str): The name of the S3 bucket for Athena data
        athena_database_name (str): The name of the Athena database
        emails_table_name (str): The name of the emails table
        email_handling_layer (Optional): Lambda layer for email processing utilities
        deploy_ses_rules (bool, optional): Whether to deploy SES receipt rules. Defaults to False.
        deploy_route53 (bool, optional): Whether to configure Route53. Defaults to False.
        **kwargs: Additional arguments passed to the Stack constructor

    Output:
        EmailAddress: The email address to send emails to
        EmailProcessorBucket: The S3 bucket name for email storage
        EmailsProcessorNotificationTopicArn: The ARN of the SNS notification topic
        EmailsProcessorLambdaLogGroup: The log group for the email processor Lambda
        EventBridgeRuleArn: The ARN of the EventBridge rule for email processing
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        project: str,
        phase: str,
        email_bucket: s3.IBucket,
        notification_topic: sns.ITopic,
        domain_name: str,
        domain_reference: str,
        athena_bucket_name_data: str,
        athena_database_name: str,
        emails_table_name: str,
        email_content_type: str,
        email_handling_layer=None,
        deploy_ses_rules: bool = False,
        deploy_route53: bool = False,
        **kwargs: Any,
    ) -> None:
        description = f"SES infrastructure for secure email ingestion, storage, and processing in the {project} pipeline"
        super().__init__(scope, id, description=description, **kwargs)

        # Capitalise first letter for tag value
        phase_tag = phase.capitalize()
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", f"{project}-EmailsProcessor")

        # Create SES role and assign permissions for S3 bucket (dependency here on s3 stack...)
        self.ses_role = iam.Role(
            self,
            "EmailsProcessorSESRole",
            assumed_by=iam.ServicePrincipal("ses.amazonaws.com"),
        )
        self.ses_role.add_to_principal_policy(
            create_s3_policy(
                bucket_arn=email_bucket.bucket_arn,
                account_id=self.account,
                region=self.region,
            )
        )

        # Add SNS publish permissions to SES role (dependency on sns stack)
        self.ses_role.add_to_principal_policy(
            create_sns_policy(
                topic_arn=notification_topic.topic_arn,
                account_id=self.account,
                region=self.region,
            )
        )
        Tags.of(self.ses_role).add("ResourceType", "IAM")
        Tags.of(self.ses_role).add("Service", "SES")

        # Dependent on state of account - if starting fresh, may need to deploy Route53 configuration and identities verification. Assumes a hosted zone
        # has already been configured separately.
        if deploy_route53:
            # Lookup hosted zone by domain name
            hosted_zone = route53.HostedZone.from_lookup(
                self, "ImportedHostedZone", domain_name=domain_name
            )

            # Verify domain with SES, configure to expect a custom mail from domain (e.g. response or mail)
            domain_identity = ses.EmailIdentity(  # noqa: F841
                self,
                "DomainIdentity",
                identity=ses.Identity.domain(domain_name),
                mail_from_domain=f"{domain_reference}.{domain_name}",
                mail_from_behavior_on_mx_failure=ses.MailFromBehaviorOnMxFailure.USE_DEFAULT_VALUE,
                dkim_signing=True,  # Makes verification easier since in same account so domain is registered for AWS to confirm automatically
            )

            # Create MX record for root domain and add text record for custom mail domain being set up following identities creation.
            # AWS Identities in SES handles CNAME via Easy DKIM so these two records must be added separately for email receiving.
            route53.MxRecord(
                self,
                "MxRecord",
                zone=hosted_zone,
                values=[
                    route53.MxRecordValue(
                        host_name=f"inbound-smtp.{self.region}.amazonaws.com",
                        priority=10,
                    )
                ],
                ttl=Duration.minutes(30),
                record_name=f"{domain_name}",
            )

            route53.TxtRecord(
                self,
                "SpfRecord",
                zone=hosted_zone,
                values=["v=spf1 include:amazonses.com ~all"],
                ttl=Duration.minutes(30),
                record_name=f"{domain_reference}.{domain_name}",
            )

            CfnOutput(
                self,
                "HostedZoneId",
                value=hosted_zone.hosted_zone_id,
                description="Route 53 hosted zone ID used for email configuration",
            )

            CfnOutput(
                self,
                "DomainVerificationStatus",
                value="Check SES console for verification status of your domain",
                description="Domain verification status in SES",
            )

        if deploy_ses_rules:
            # Create SES Receipt Rule Set for account. Remember to set it as active manually in console!
            self.rule_set = ses.ReceiptRuleSet(
                self,
                "MasterRuleSet",
                rules=[
                    ses.ReceiptRuleOptions(
                        recipients=[f"incoming@{domain_name}"],
                        actions=[
                            actions.S3(
                                bucket=email_bucket,
                                object_key_prefix="incoming/",
                                topic=notification_topic,
                            )
                        ],
                        enabled=True,
                    )
                ],
            )
            self.rule_set.apply_removal_policy(
                RemovalPolicy.RETAIN
            )  # To avoid deployment/destruction issues, we create a new one with each deployment

        # Lambda function to process emails and write to S3 bucket for project in London
        email_processor = _lambda.Function(
            self,
            f"{project}-EmailsProcessor",
            function_name=f"{project}-email-processor",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.Code.from_asset("./lambda/lambda_emails/handler"),
            timeout=Duration.seconds(300),
            environment={
                "ATHENA_DATABASE": athena_database_name,
                "ATHENA_TABLE": emails_table_name,
                "ATHENA_OUTPUT_BUCKET": athena_bucket_name_data,
                "SOURCE_BUCKET": email_bucket.bucket_name,
                "PROJECT": project,
                "TARGET_REGION": "eu-west-2",  # Add this for cross-region writes
                "EMAIL_CONTENT_TYPE": email_content_type
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
            layers=[email_handling_layer],
        )
        Tags.of(email_processor).add("ResourceType", "Function")
        Tags.of(email_processor).add("Service", "Lambda")

        # Grant permissions
        email_bucket.grant_read(email_processor)

        # Add cross-region permission to write to Athena bucket
        email_processor.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject"],
                resources=[f"arn:aws:s3:::{athena_bucket_name_data}/*"],
            )
        )

        # Create EventBridge rule for S3 object creation in the incoming folder
        # This rule will trigger the Lambda function when any object is created in the incoming/ folder
        s3_event_rule = events.Rule(
            self,
            f"{project}-S3ObjectCreatedRule",
            description=f"Rule for processing new emails for {project}",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [email_bucket.bucket_name]},
                    "object": {"key": [{"prefix": "incoming/"}]},
                },
            ),
        )

        # Add the Lambda function as a target for the EventBridge rule
        s3_event_rule.add_target(
            targets.LambdaFunction(email_processor, retry_attempts=2)
        )

        email_processor.add_permission(
            f"{project}-EventBridgeInvokePermission",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            source_arn=s3_event_rule.rule_arn,
            action="lambda:InvokeFunction",
        )

        # Remember, if using a domain, need to add the MX record for the hosted zone
        # since using dev.cddo-af.data.gov.uk. AWS SES adds some to route53 existing zones but needs an extra smtp incoming.
        # This covers what needs to go into it: https://docs.aws.amazon.com/ses/latest/dg/receiving-email-mx-record.html

        # Outputs
        CfnOutput(
            self,
            "EmailAddress",
            value="incoming@dev.cddo-af.data.gov.uk",
            description="Send emails to this address",
        )

        CfnOutput(
            self,
            "EmailProcessorBucket",
            value=email_bucket.bucket_name,
            description="S3 bucket containing received emails",
        )

        CfnOutput(
            self,
            "EmailsProcessorNotificationTopicArn",
            value=notification_topic.topic_arn,
            description="SNS topic for email notifications",
        )

        CfnOutput(
            self,
            "EmailsProcessorLambdaLogGroup",
            value=email_processor.log_group.log_group_name,
            description="CloudWatch Log Group for Lambda function",
        )

        CfnOutput(
            self,
            "EventBridgeRuleArn",
            value=s3_event_rule.rule_arn,
            description=f"EventBridge rule for {project} email processing",
        )
