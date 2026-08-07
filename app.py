import aws_cdk as cdk

from stacks.incoming.ses_infra import SESEmailsStack
from stacks.incoming.ses_layer import EmailLayerStack
from stacks.incoming.ses_s3 import S3EmailsStack
from stacks.incoming.ses_sns import SNSEmailsStack
from stacks.llm.knowledge_base import DocumentKnowledgeBaseStack
from stacks.llm.llm_image import LLMDockerImageStack
from stacks.llm.llm_lambda import LLMLambdaFunctionsStack
from stacks.llm.llm_storage import LLMStorageStack
from stacks.outgoing.outgoing_lambda import OutgoingLambdaFunctionsStack
from stacks.outgoing.sender_image import SenderDockerImageStack
from stacks.secrets import NotifySecretStack
from stacks.storage import StorageStack

app = cdk.App()

# Get development phase and project from context
phase = app.node.try_get_context("phase")
project = app.node.try_get_context("project")

# Extract information required dependent on phase/account
if phase == "prod":
    account_number = app.node.try_get_context("prod_account_number")
    domain_name = app.node.try_get_context("prod_domain_name")
    domain_reference = app.node.try_get_context("prod_domain_reference")
else:
    account_number = app.node.try_get_context(
        "dev_account_number"
    )  # Use the default account_number for dev
    domain_name = app.node.try_get_context("dev_domain_name")
    domain_reference = app.node.try_get_context("dev_domain_reference")

# Environment configuration
data_env = cdk.Environment(
    account=account_number,
    region=app.node.try_get_context("data_region"),
)

# Get storage contexts
athena_database_name = app.node.try_get_context("athena_database") + "_" + phase
athena_bucket_name_emails = (
    app.node.try_get_context("s3_bucket_emailinbox") + "-" + phase
)  # Bucket to hold incoming email content
athena_bucket_name_data = (
    app.node.try_get_context("athena_s3_bucket_data") + "-" + phase
)  # Bucket to store data/queries on processed email data
email_content_table = app.node.try_get_context("athena_table_name_emails")
email_content_type = app.node.try_get_context("email_content_type")

athena_workgroup = app.node.try_get_context(
    "athena_workgroup"
)  # enable/disable athena workgroup

print(f"athena_workgroup value: {athena_workgroup}")

# Set up email subscriptions - check which type it is, single or a list of names...
topic_name = app.node.try_get_context("sns_topic_name") + "-" + phase
notification_emails_context = app.node.try_get_context("notification_email")
if isinstance(notification_emails_context, str):
    notification_emails = [notification_emails_context]
elif isinstance(notification_emails_context, list):
    notification_emails = notification_emails_context
else:
    notification_emails = []

# If active SES ruleset in place, don't try to overwrite it/delete it
deploy_infrastructure = (
    app.node.try_get_context("deploy_ses_infrastructure").lower() == "true"
)
deploy_emails_bucket = (
    app.node.try_get_context("deploy_emails_bucket").lower() == "true"
    and deploy_infrastructure
)
deploy_sns_topic = (
    app.node.try_get_context("deploy_sns_topic").lower() == "true"
    and deploy_infrastructure
)
update_sns_subscription = (
    app.node.try_get_context("update_sns_subscription").lower() == "true"
)
deploy_ses_rules = (
    app.node.try_get_context("deploy_ses_rules").lower() == "true"
    and deploy_infrastructure
)
deploy_route53 = (
    app.node.try_get_context("deploy_route53").lower() == "true"
    and deploy_infrastructure
)

# LLM deployment with RAG
deploy_llm = app.node.try_get_context("deploy_llm").lower() == "true"
documentstore = (
    app.node.try_get_context("athena_s3_bucket_data")
    + "-"
    + "documentstore"
    + "-"
    + phase
)

# Email sender/responder deployment
deploy_sender = app.node.try_get_context("deploy_sender").lower() == "true"
sender_mode = app.node.try_get_context("sender_mode")

# Depending on cdk.json context, set booleans for what is to be deployed

print(f"athena_bucket_name_emails: {athena_bucket_name_emails}")
print(f"athena_bucket_name_data: {athena_bucket_name_data}")
print(f"athena_database_name: {athena_database_name}")
print(f"email_content_table: {email_content_table}")
print(f"sender_mode: {sender_mode}")

# Create project specific s3 and athena database tables
storage_stack = StorageStack(
    app,
    f"{project}-StorageStack",
    phase=phase,
    project=project,
    athena_database_name=athena_database_name,
    athena_bucket_name=athena_bucket_name_data,
    emails_table_name=email_content_table,
    athena_workgroup=athena_workgroup,
    env=data_env,
)

# Deploy emails s3 bucket if starting from scratch, otherwise associate emails with project
emails_s3_stack = S3EmailsStack(
    app,
    f"{project}-S3Stack-{phase}",
    athena_bucket_name_emails=athena_bucket_name_emails,
    phase=phase,
    project=project,
    deploy_bucket=deploy_emails_bucket,
    env=data_env,
)

# Always create/update SNS Stack as there may well be new subscriptions to be made and we want to track incoming emails to someone!
sns_stack = SNSEmailsStack(
    app,
    f"{project}-SNSStack-{phase}",
    notification_emails=notification_emails,
    phase=phase,
    project=project,
    topic_name=topic_name,
    deploy_topic=deploy_sns_topic,
    update_subscription=update_sns_subscription,
    env=data_env,
)

# Deploy Emails Layer Stack to same region as SES
layer_stack = EmailLayerStack(
    app,
    f"{project}-LayerStack",
    project=project,
    phase=phase,
    env=data_env,
)

# Deploy SES Stack
if deploy_infrastructure:
    ses_stack = SESEmailsStack(
        app,
        f"{project}-SESStack",
        project=project,
        domain_name=domain_name,
        domain_reference=domain_reference,
        email_bucket=emails_s3_stack.email_bucket,
        notification_topic=sns_stack.notification_topic,
        athena_bucket_name_data=athena_bucket_name_data,
        athena_database_name=athena_database_name,
        emails_table_name=email_content_table,
        email_content_type=email_content_type,
        email_handling_layer=layer_stack.email_handling_layer,
        deploy_ses_rules=deploy_ses_rules,
        deploy_route53=deploy_route53,
        phase=phase,
        env=data_env,
    )
    ses_stack.add_dependency(layer_stack)


# Deploy LLM-based functionality if set
if deploy_llm:
    llm_responses_table = app.node.try_get_context("athena_table_name_responses")
    llm_region = app.node.try_get_context("llm_region")
    kb_name = (
        project[:6] + phase[:3]
    )  # knowledge base name reference can only be 10 characters max

    # Check status of knowledge base, has it already been deployed and has an ID?
    kb_id = app.node.try_get_context("kb_id_exists")
    kb_id_valid = kb_id not in ["", None, "false", "False"]
    knowledge_stack = DocumentKnowledgeBaseStack(
        app,
        f"{project}-KnowledgeBaseStack",
        project=project,
        kb_name=kb_name,
        document_bucket=documentstore,
        phase=phase,
    )

    llm_storage_stack = LLMStorageStack(
        app,
        f"{project}-LLMStorageStack",
        project=project,
        phase=phase,
        responses_table_name=llm_responses_table,
        athena_database_name=athena_database_name,
        athena_bucket_name_data=athena_bucket_name_data,
    )
    llm_storage_stack.add_dependency(storage_stack)

    # Deploy the Docker Images stack
    llm_images_stack = LLMDockerImageStack(
        app,
        f"{project}-DockerImagesStack-{phase}",
        phase=phase,
        project=project,
        env=data_env,
    )
    if kb_id_valid:
        if not (kb_id.isalnum() and len(kb_id) <= 10):
            print(
                f"⚠️  WARNING: Knowledge Base ID '{kb_id}' is not in the correct format!"
            )
            print("   The KB ID must be alphanumeric and 10 characters or less.")
            print(
                "   Deploy the knowledge base first and then amend cdk.json to use the newly created KB ID."
            )
        else:
            print(f"✅ Knowledge Base ID configured correctly: {kb_id}")
            lambda_functions_stack = LLMLambdaFunctionsStack(
                app,
                f"{project}-LambdaFunctionsStack-{phase}",
                llm_region=llm_region,
                athena_database=athena_database_name,
                athena_queries_bucket=athena_bucket_name_data,
                athena_bucket=storage_stack.athena_bucket,
                llm_image_asset=llm_images_stack.llm_responder_asset,
                queries_table_name=email_content_table,
                responses_table_name=llm_responses_table,
                kb_id=kb_id,
                phase=phase,
                project=project,
                env=data_env,  # Pass the data region in for the knowledge base
            )
            lambda_functions_stack.add_dependency(storage_stack)
            lambda_functions_stack.add_dependency(knowledge_stack)
            lambda_functions_stack.add_dependency(llm_images_stack)

    else:
        print("⚠️  WARNING: Knowledge Base ID is not configured!")
        print(
            "   Without a valid ID, your Lambda function will fail when trying to use the knowledge base."
        )
if deploy_sender:
    email_subject = app.node.try_get_context("sender_subject")
    sender_email_address = domain_reference + "@" + domain_name
    followup_email_address = app.node.try_get_context("followup_email_address")

    # Initialise variables for Notify mode
    secrets_stack = None
    api_key_name = None
    api_key_arn = None
    notify_template_id = None

    # If using Notify mode, create secrets stack and get Notify configuration
    if sender_mode == "notify":
        api_key_name = app.node.try_get_context("notify_apikey_name")
        notify_template_id = app.node.try_get_context("notify_template_id")

        if not api_key_name:
            raise ValueError(
                "valid notify_apikey_name must be specified in cdk.json when using notify mode"
            )
        if not notify_template_id:
            raise ValueError(
                "valid notify_template_id must be specified in cdk.json when using notify mode"
            )

        # Create Secrets Stack for Notify API key
        secrets_stack = NotifySecretStack(
            app,
            f"{project}-SecretStack",
            phase=phase,
            api_key_name=api_key_name,
            env=data_env,
        )
        api_key_arn = secrets_stack.notify_secret.secret_arn

    sender_image_stack = SenderDockerImageStack(
        app,
        f"{project}-SenderDockerImagesStack-{phase}",
        phase=phase,
        project=project,
        env=data_env,
    )

    sender_lambda_stack = OutgoingLambdaFunctionsStack(
        app,
        f"{project}-SenderLambdaFunctionsStack-{phase}",
        athena_database=athena_database_name,
        athena_bucket=storage_stack.athena_bucket,
        sender_lambda_image_asset=sender_image_stack.email_sender_asset,
        responses_table_name=llm_responses_table,
        domain_name=domain_name,
        email_subject=email_subject,
        followup_email_address=followup_email_address,
        sender_email_address=sender_email_address,
        sender_mode=sender_mode,
        api_key_name=api_key_name,
        api_key_arn=api_key_arn,
        notify_template_id=notify_template_id,
        phase=phase,
        project=project,
        env=data_env,
    )
    sender_lambda_stack.add_dependency(sender_image_stack)

    # Add dependency on secrets stack if using Notify
    if secrets_stack:
        sender_lambda_stack.add_dependency(secrets_stack)

app.synth()
