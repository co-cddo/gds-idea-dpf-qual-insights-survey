from typing import Any
from aws_cdk import CfnOutput, Stack, Tags
from aws_cdk import (
    aws_ecr_assets as ecr_assets,
)
from constructs import Construct


# TODO: Amend this so we have docker image settings in this place, and lambda functions defined in snapshot functions.py aside from the email lambda which doesn't use
# images
class SenderDockerImageStack(Stack):
    """Creates Docker image assets for email sender Lambda functions.

    This stack builds and registers Docker images that are used by Lambda functions
    for sending email responses. The images contain all the required dependencies and code for
    the Lambda functions.

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        phase (str): Deployment phase (e.g., "dev", "prod")
        project (str): The project name used for resource naming and tagging
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        email_sender_asset: The Docker image asset for the email sender Lambda function

    Output:
        EmailSenderImageRepo: The ECR repository URI for the Docker image
        EmailSenderImageTag: The image tag for the Docker image
        EmailSenderFullImageURI: The full URI for the Docker image
    """
    def __init__(
        self,
        scope: Construct,
        id: str,
        phase: str,
        project: str,
        **kwargs: Any,
    ) -> None:
        description = f"Stack containing Docker image assets for {project} Sender Lambda functions"

        super().__init__(scope, id, description=description, **kwargs)

        # Tag the stack resources for cost allocation and management
        phase_tag = phase.capitalize()
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", f"{project}-Images")

        self.email_sender_asset = ecr_assets.DockerImageAsset(
            self,
            f"{project}-EmailSenderLambdaImage",
            directory="./lambda/sender",
        )
        Tags.of(self.email_sender_asset).add("ResourceType", "DockerImage")
        Tags.of(self.email_sender_asset).add("Service", "ECR")

        # Add outputs to show where the image is located
        CfnOutput(
            self,
            "EmailSenderImageRepo",
            value=self.email_sender_asset.repository.repository_uri,
            description="Repository URI for the email sender Docker image",
        )

        CfnOutput(
            self,
            "EmailSenderImageTag",
            value=self.email_sender_asset.image_tag,
            description="Image tag for the email sender Docker image",
        )

        CfnOutput(
            self,
            "EmailSenderFullImageURI",
            value=f"{self.email_sender_asset.repository.repository_uri}:{self.email_sender_asset.image_tag}",
            description="Full URI for the email sender Docker image",
        )
