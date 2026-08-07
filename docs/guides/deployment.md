# EZComms Deployment Guide

This guide explains how to deploy the EZComms system using AWS CDK with configuration-driven deployment.

## Deployment Overview

EZComms uses a unified deployment approach where all components are deployed using `cdk deploy --all`, with configuration toggles in `cdk.json` controlling which resources are created. This eliminates the need for staged deployments while maintaining proper dependency management.

## Pre-Deployment Configuration

Before deploying, configure your system by editing the `cdk.json` file. See the [Configuration Guide](configuration.md) for detailed information about all available options.

### Required Configuration Steps

1. **Set Environment Variables**: Configure your target environment (`dev` or `prod`) and associated account/domain settings
2. **Configure Feature Toggles**: Enable or disable components based on your requirements
3. **Set Resource Names**: Customize bucket names, database names, and other identifiers
4. **Choose Email Sending Mode**: Select between `"ses"` or `"notify"` for the `sender_mode` parameter

### Critical Configuration for LLM Features

If deploying LLM functionality (`deploy_llm: true`):

1. **Initial Deployment**: Set `kb_id_exists` to `false` or leave empty for the first deployment
2. **Post-Knowledge Base Creation**: After the first deployment creates your knowledge base, update `kb_id_exists` with the generated ID
3. **Redeploy**: Run deployment again to enable full LLM functionality

### GOV.UK Notify Setup (If Using Notify Mode)

If using `sender_mode: "notify"`:

1. **Create Notify Account**: Sign up at [notifications.service.gov.uk](https://www.notifications.service.gov.uk/)
2. **Create Email Template**: 
   - Create a new email template in your Notify account
   - Add personalisation fields: `((question))` and `((response))`
   - Note the template ID from the template settings or URL
3. **Generate API Key**: 
   - Create an API key in your Notify account settings
   - Use Team and whitelist key for testing, Live key for production
   - Keep this key secure - you'll need it after deployment
4. **Update cdk.json**:
   ```json
   "sender_mode": "notify",
   "notify_apikey_name": "ezcomms_notify_api_key",
   "notify_template_id": "your-template-id-here"
   ```

## Deployment Commands

### Single Unified Deployment

For most deployments, use the unified approach:

```bash
cdk deploy --all
```

This command will:
- Read all configuration from `cdk.json`
- Deploy only the components enabled by feature toggles
- Respect all stack dependencies automatically
- Handle conditional resource creation

### Selective Deployment

If you need to deploy specific stacks (advanced usage):

```bash
# Deploy specific stacks by name
cdk deploy ezcomms-StorageStack ezcomms-SNSStack-dev

# Deploy with approval prompts disabled (useful for CI/CD)
cdk deploy --all --require-approval never
```

## Understanding the Deployment Process

### How app.py Orchestrates Deployment

The `app.py` file acts as the deployment orchestrator:

1. **Configuration Processing**: Reads all settings from `cdk.json`
2. **Environment Resolution**: Determines target AWS account and region based on phase
3. **Conditional Stack Creation**: Creates only the stacks enabled by feature toggles
4. **Dependency Management**: Automatically handles dependencies between stacks
5. **Resource Validation**: Validates critical configuration values (e.g., Knowledge Base ID format)

### Feature Toggle Logic

Stacks are created conditionally based on these toggles:

| Feature Toggle | Stacks Created | Additional Requirements |
|----------------|----------------|------------------------|
| Always deployed | StorageStack, S3EmailsStack, SNSEmailsStack, EmailLayerStack | None |
| `deploy_ses_infrastructure: true` | SESEmailsStack | Requires EmailLayerStack |
| `deploy_emails_bucket: true` | Creates new S3 bucket (otherwise references existing) | Requires `deploy_ses_infrastructure: true` |
| `deploy_sns_topic: true` | Creates new SNS topic (otherwise references existing) | Requires `deploy_ses_infrastructure: true` |
| `deploy_llm: true` | DocumentKnowledgeBaseStack, LLMStorageStack, LLMDockerImageStack | Requires StorageStack |
| `deploy_llm: true` + valid `kb_id_exists` | LLMLambdaFunctionsStack | Requires all LLM stacks + valid KB ID |
| `deploy_sender: true` | SenderDockerImageStack, OutgoingLambdaFunctionsStack | None (independent) |
| `deploy_sender: true` + `sender_mode: "notify"` | NotifySecretStack | Required for Notify mode |

### Stack Dependencies

The deployment automatically handles these dependencies:

```
Always Deployed:
├── StorageStack (foundation)
├── S3EmailsStack (references or creates bucket based on deploy_emails_bucket)
├── SNSEmailsStack (references or creates topic based on deploy_sns_topic)
└── EmailLayerStack

Conditional Stacks:
├── SESEmailsStack (if deploy_ses_infrastructure: true)
│   └── depends on: EmailLayerStack
├── LLM Components (if deploy_llm: true)
│   ├── DocumentKnowledgeBaseStack (independent)
│   ├── LLMStorageStack
│   │   └── depends on: StorageStack
│   ├── LLMDockerImageStack (independent)
│   └── LLMLambdaFunctionsStack (if kb_id_exists is valid)
│       ├── depends on: StorageStack
│       ├── depends on: DocumentKnowledgeBaseStack  
│       └── depends on: LLMDockerImageStack
└── Sender Components (if deploy_sender: true)
    ├── NotifySecretStack (if sender_mode: "notify")
    ├── SenderDockerImageStack (independent)
    └── OutgoingLambdaFunctionsStack
        ├── depends on: SenderDockerImageStack
        └── depends on: NotifySecretStack (if using Notify)
```

## Environment-Specific Deployment

### Development Environment
```json
"phase": "dev"
```
Uses: `dev_account_number`, `dev_domain_name`, `dev_domain_reference`

### Production Environment
```json
"phase": "prod"
```
Uses: `prod_account_number`, `prod_domain_name`, `prod_domain_reference`

## Post-Deployment Tasks

### Capture Important Outputs

After deployment, CDK will output critical information:

- **Knowledge Base ID**: Required for updating `cdk.json` if deploying LLM features
- **S3 Bucket Names**: For reference in other systems
- **SNS Topic ARN**: For external integrations
- **Lambda Function Names**: For monitoring and debugging

### Update Configuration for LLM Features

If you deployed with `deploy_llm: true` and this was your first deployment:

1. Note the Knowledge Base ID from the deployment outputs
2. Update `cdk.json`: set `"kb_id_exists": "YOUR_KB_ID"`
3. Redeploy: `cdk deploy --all`

This two-step process is necessary because the Knowledge Base ID is generated during the first deployment and is required for subsequent LLM Lambda function configuration.

### Set GOV.UK Notify API Key (If Using Notify Mode)

If you deployed with `sender_mode: "notify"`, you must set the Notify API key in AWS Secrets Manager:

1. **Locate the Secret**: The deployment will create a secret with the name specified in `notify_apikey_name`

2. **Set the API Key**:
   ```bash
   aws secretsmanager put-secret-value \
     --secret-id ezcomms_notify_api_key \
     --secret-string 'your-actual-notify-api-key' \
     --region eu-west-2
   ```

3. **Verify the Secret**:
   ```bash
   aws secretsmanager describe-secret \
     --secret-id notify_apikey_name \
     --region eu-west-2
   ```

4. **Test Email Sending**: Trigger the Lambda function to verify Notify integration is working

**Important**: Without setting this API key, the email sender Lambda will fail when attempting to send emails via Notify.

## Common Deployment Scenarios

### Email Processing Only
```json
{
  "deploy_ses_infrastructure": "true",
  "deploy_emails_bucket": "true", 
  "deploy_sns_topic": "true",
  "deploy_llm": "false",
  "deploy_sender": "false"
}
```

### Full System with LLM and Auto-Response
```json
{
  "deploy_ses_infrastructure": "true",
  "deploy_emails_bucket": "true",
  "deploy_sns_topic": "true", 
  "deploy_llm": "true",
  "kb_id_exists": "YOUR_KB_ID",
  "deploy_sender": "true"
}
```

### Incremental Feature Addition
Start with basic email processing, then add features by updating toggles and redeploying:

1. Deploy with email processing only
2. Update `deploy_llm: true`, redeploy to add LLM features
3. Update `kb_id_exists` with generated ID, redeploy to enable LLM processing
4. Update `deploy_sender: true`, redeploy to add auto-response capability

## Verification and Testing

### Post-Deployment Verification

1. **S3 Buckets**: Verify correct bucket creation and naming
2. **SES Configuration**: Confirm domain identity verification and rules
3. **SNS Subscriptions**: Test notification email delivery
4. **LLM Integration**: Verify knowledge base connectivity (if deployed)
5. **Auto-Response**: Test end-to-end email processing and response (if deployed)

### Testing Commands

```bash
# List all deployed stacks
cdk list

# Check stack status
aws cloudformation describe-stacks --stack-name ezcomms-StorageStack

# Verify SES domain identity
aws ses get-identity-verification-attributes --identities your-domain.com

# Check Notify secret (if using Notify)
aws secretsmanager describe-secret --secret-id ezcomms_notify_api_key
```

## Troubleshooting

### Knowledge Base Configuration Issues

**Warning: Knowledge Base ID is not configured**
- Deploy without LLM features first, capture the generated KB ID, then update configuration and redeploy

**Warning: Knowledge Base ID format invalid**
- Ensure the ID is alphanumeric and ≤10 characters

### Resource Creation Issues

**Stacks not being created**
- Verify feature toggles are set to `"true"` (string, not boolean)
- Check for dependency requirements (e.g., `deploy_emails_bucket` requires `deploy_ses_infrastructure`)

**Permission errors**
- Ensure AWS credentials have sufficient permissions for all resource types being deployed
- Verify IAM permissions for Bedrock model access (if using LLM features)

### SES Configuration Issues

**Email receiving not working**
- Confirm domain verification in SES console
- Check MX records are properly configured
- Verify SES rules are active (if `deploy_ses_rules: true`)

### GOV.UK Notify Issues

**Lambda fails with "Missing required environment variables"**
- Verify `notify_apikey_name` and `notify_template_id` are set in `cdk.json`
- Check that `sender_mode` is set to `"notify"`

**"Could not find secret" errors**
- Ensure you've set the API key in Secrets Manager after deployment
- Verify the secret name matches `notify_apikey_name` in `cdk.json`

**"Template not found" errors**
- Verify the template ID in `cdk.json` matches the template ID in your Notify account
- Check that the template has the required personalisation fields: `((question))` and `((response))`

**Emails not sending via Notify**
- Check CloudWatch Logs for the Lambda function for detailed error messages
- Verify your Notify API key is valid and has the correct permissions
- If using a Team and whitelist key, ensure the recipient email is in your team
- Check the GOV.UK Notify dashboard for delivery status

## Cleanup

### Complete Resource Removal

```bash
cdk destroy --all
```

**⚠️ Warning**: This will permanently delete all resources, including data stored in S3 buckets. Ensure you have backups of any important data before running this command.

### Selective Resource Removal

To remove specific components, update feature toggles to `false` and redeploy:

```json
{
  "deploy_llm": "false",  // This will remove LLM-related resources
  "deploy_sender": "false"  // This will remove sender-related resources
}
```

Then run: `cdk deploy --all`

This approach is safer as it allows you to remove components incrementally while preserving data and other resources.

### Manual Cleanup for Failed Deletions

If stack deletion fails (e.g., you see `ROLLBACK_UPDATE_FAILED` or similar errors), you can manually delete stacks through the AWS CloudFormation console:

1. **Access CloudFormation Console**: Navigate to AWS CloudFormation in your target region
2. **Identify Failed Stacks**: Look for stacks with `DELETE_FAILED` or `ROLLBACK_UPDATE_FAILED` status
3. **Delete in Dependency Order**: Delete stacks in reverse order of their dependencies to avoid cascading failures

#### Recommended Deletion Order

Follow this order to respect stack dependencies:

```
1. OutgoingLambdaFunctionsStack (if deployed)
2. SenderDockerImageStack (if deployed)
3. NotifySecretStack (if deployed with Notify mode)
4. LLMLambdaFunctionsStack (if deployed)
5. LLMDockerImageStack (if deployed)
6. LLMStorageStack (if deployed)
7. DocumentKnowledgeBaseStack (if deployed)
8. SESEmailsStack (if deployed)
9. EmailLayerStack
10. SNSEmailsStack
11. S3EmailsStack
12. StorageStack (delete last - foundation stack)
```

#### Manual Deletion Steps

1. **Select Stack**: Choose the stack to delete from the CloudFormation console
2. **Delete Stack**: Click "Delete" and confirm the action
3. **Monitor Progress**: Watch for deletion completion or new errors
4. **Handle Resource Dependencies**: If deletion fails due to resource dependencies:
   - Check which resources are preventing deletion
   - Manually delete dependent resources if safe to do so
   - Retry stack deletion

#### Common Deletion Issues

- **S3 Buckets Not Empty**: Empty buckets manually before stack deletion, or ensure `auto_delete_objects: True` was set during deployment
- **Lambda Functions with ENIs**: Wait for Elastic Network Interfaces to be released (can take 10-15 minutes)
- **IAM Roles in Use**: Ensure no active services are using IAM roles created by the stack
- **SES Rules Active**: Disable active SES receipt rules before deleting SES-related stacks

#### Force Deletion (Last Resort)

If manual deletion continues to fail:

1. **Skip Resource Deletion**: In CloudFormation console, choose to skip problematic resources during stack deletion
2. **Manual Resource Cleanup**: After stack deletion, manually clean up any remaining resources through their respective AWS service consoles
3. **Cost Monitoring**: Monitor AWS billing to ensure no unexpected charges from orphaned resources

**Note**: Skipping resource deletion may result in orphaned AWS resources that continue to incur charges. Always verify complete cleanup through the AWS billing dashboard.