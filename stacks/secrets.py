from typing import Any

from aws_cdk import CfnOutput, Stack
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class NotifySecretStack(Stack):
    """Stack for managing GOV.UK Notify API key in AWS Secrets Manager.

    This stack creates a secret to store the GOV.UK Notify API key that will be
    used for sending email notifications. The actual key value must be set manually
    after stack deployment using the AWS CLI or Console.

    Args:
        scope (Construct): The parent AWS CDK construct
        construct_id (str): The construct ID for this stack
        phase (str): Deployment phase (e.g., "dev", "prod")
        api_key_name (str): Name for the Secrets Manager secret
        **kwargs: Additional arguments passed to the Stack constructor
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        phase: str,
        api_key_name: str,
        **kwargs: Any,
    ) -> None:
        description = (
            "AWS Secrets Manager infrastructure for handling GOV.UK Notify API key"
        )
        super().__init__(scope, construct_id, description=description, **kwargs)

        # Create secret for Notify API access
        self.notify_secret = secretsmanager.Secret(
            self,
            "NotifyAPISecret",
            secret_name=f"{api_key_name}",
            description="GOV.UK Notify API key for email notifications",
        )

        CfnOutput(
            self,
            "NotifySecretName",
            value=self.notify_secret.secret_name,
            description="Name of the GOV.UK Notify API key secret",
            export_name=f"{construct_id}-SecretName",
        )

        CfnOutput(
            self,
            "SetSecretCommand",
            value=f"aws secretsmanager put-secret-value --secret-id {api_key_name} --secret-string 'YOUR_NOTIFY_API_KEY_NAME' --region {self.region}",
            description="Command to set the GOV.UK Notify API key value",
        )
