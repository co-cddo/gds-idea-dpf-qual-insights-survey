from typing import Any
from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_s3 as s3
from constructs import Construct


class S3EmailsStack(Stack):
    """Creates or references an S3 bucket for storing incoming emails.

    This stack either creates a new S3 bucket for storing emails or references an
    existing bucket by name. The bucket is used to store raw emails received by SES.

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        athena_bucket_name_emails (str): The name for the S3 bucket storing emails
        phase (str): Deployment phase (e.g., "dev", "prod")
        project (str): The project name used for resource naming and tagging
        deploy_bucket (bool, optional): Whether to create a new bucket or reference an existing one. Defaults to True.
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        email_bucket: The S3 bucket for storing emails (either created or imported)

    Output:
        S3BucketName: The name of the S3 bucket for email storage
    """
    def __init__(
        self,
        scope: Construct,
        id: str,
        athena_bucket_name_emails: str,
        phase: str,
        project: str,
        deploy_bucket: bool = True,
        **kwargs: Any,
    ) -> None:
        description = (
            f"Stack referencing {project} S3 bucket for incoming emails handling"
        )
        super().__init__(scope, id, description=description, **kwargs)

        # Capitalise first letter for tag value
        phase_tag = phase.capitalize()

        # Add tags to the entire stack
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", "Master-Email-Infrastructure")

        if deploy_bucket:
            # Create new S3 bucket to capture emails
            self.email_bucket = s3.Bucket(
                self,
                "EmailProcessorBucket",
                bucket_name=athena_bucket_name_emails,
                removal_policy=RemovalPolicy.DESTROY,
                event_bridge_enabled=True,  # Enable EventBridge integration
            )
            Tags.of(self.email_bucket).add("ResourceType", "Storage")
            Tags.of(self.email_bucket).add("Service", "S3")
        else:
            # Import existing bucket instead of creating a new one
            self.email_bucket = s3.Bucket.from_bucket_name(
                self, "ImportedEmailProcessorBucket", athena_bucket_name_emails
            )

        # Outputs
        CfnOutput(
            self,
            "S3BucketName",
            value=self.email_bucket.bucket_name,
            description="S3 bucket containing received emails",
        )
