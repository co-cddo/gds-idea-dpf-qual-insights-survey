from typing import Any
from aws_cdk import (
    Stack,
    Tags,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from aws_cdk import (
    aws_lambda_python_alpha as _alambda,
)
from constructs import Construct


class EmailLayerStack(Stack):
    """Creates the Lambda layer infrastructure for email processing functionality.

    This stack sets up a reusable Lambda layer that contains Python packages for email
    processing. The layer can be used by multiple Lambda functions that need to process
    email content.

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        project (str): The project name used for resource naming and tagging
        phase (str, optional): Deployment phase (e.g., "dev", "prod"). Defaults to "dev".
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        email_handling_layer: The created Lambda layer version that can be attached to Lambda functions
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        project: str,
        phase: str = "dev",
        **kwargs: Any,
    ) -> None:
        description = f"Lambda layer infrastructure for email processing functionality in the {project} pipeline"
        super().__init__(scope, id, description=description, **kwargs)

        # Capitalise first letter for tag value
        phase_tag = phase.capitalize()

        # Add tags to the entire stack
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", f"{project}-EmailsLayer")

        # Create email processing layer
        self.email_handling_layer = _alambda.PythonLayerVersion(
            self,
            f"{project}-EmailsLayer",
            layer_version_name=f"{project}-email-handler-layer",
            entry="./lambda/lambda_emails/layer",
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            compatible_architectures=[_lambda.Architecture.X86_64],
            description="Layer containing email processing packages.",
        )
        Tags.of(self.email_handling_layer).add("ResourceType", "Layer")
        Tags.of(self.email_handling_layer).add("Service", "Lambda")
