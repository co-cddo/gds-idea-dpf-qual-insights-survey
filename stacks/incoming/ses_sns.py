from typing import Any
from aws_cdk import CfnOutput, Stack, Tags
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct


class SNSEmailsStack(Stack):
    """Creates or references an SNS topic for email notifications.

    This stack either creates a new SNS topic for email notifications or references an
    existing topic by name. The topic is used to send notifications when emails are
    received, and can have email subscriptions added for notification delivery.

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        notification_emails (list): List of email addresses to subscribe to the topic
        phase (str): Deployment phase (e.g., "dev", "prod")
        project (str): The project name used for resource naming and tagging
        topic_name (str, optional): Custom name for the SNS topic. Defaults to None.
        deploy_topic (bool, optional): Whether to create a new topic or reference an existing one. Defaults to True.
        update_subscription (bool, optional): Whether to update existing subscriptions. Defaults to True.
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        notification_topic: The SNS topic for email notifications

    Output:
        SNSTopicArn: The ARN of the SNS topic for email notifications
    """
    def __init__(
        self,
        scope: Construct,
        id: str,
        notification_emails: list,
        phase: str,
        project: str,
        topic_name: str = None,
        deploy_topic: bool = True,
        update_subscription: bool = True,
        **kwargs: Any,
    ) -> None:
        description = f"Stack containing {project} SNS topic for general incoming email notifications"
        super().__init__(scope, id, description=description, **kwargs)

        # Capitalise first letter for tag value and add tags for tracking usage and cost
        phase_tag = phase.capitalize()
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", "Master-Email-Infrastructure")

        default_topic_name = f"Master-IncomingEmails-{phase}"

        if deploy_topic:
            self.notification_topic = sns.Topic(
                self,
                default_topic_name,
                display_name="Incoming Email Notifications",
                topic_name=topic_name or default_topic_name,
            )
            Tags.of(self.notification_topic).add("ResourceType", "Messaging")
            Tags.of(self.notification_topic).add("Service", "SNS")
        else:
            # Import existing topic instead of creating a new one if we already have infrastructure set up, just need to add more names
            topic_arn = f"arn:aws:sns:{self.region}:{self.account}:{topic_name or default_topic_name}"
            self.notification_topic = sns.Topic.from_topic_arn(
                self, "ImportedTopic", topic_arn
            )

        # Add or update subscription regardless if the topic is new or imported
        if update_subscription:
            for email in notification_emails:
                self.notification_topic.add_subscription(
                    subscriptions.EmailSubscription(email)
                )

        # Outputs
        CfnOutput(
            self,
            "SNSTopicArn",
            value=self.notification_topic.topic_arn,
            description="SNS topic for email notifications",
        )
