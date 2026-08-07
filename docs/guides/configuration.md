# EZComms Configuration Guide

This guide explains how to configure the EZComms system ahead of deployment using the `cdk.json` file, which provides context variables that control how the system is deployed, which modules are deployed, and how the overall pipeline operates.

## Configuration Overview

EZComms is designed to be highly configurable through context variables in the `cdk.json` file. These variables control everything from AWS account information to feature toggles and naming conventions.

The `app.py` file reads these variables and conditionally creates the AWS resources based on your configuration choices.

## Account and Domain Configuration

EZComms supports both development and production environments, controlled by the `phase` variable.

```json
"phase": "dev",  // Options: "dev" or "prod"
"project": "ezcomms"
```

Depending on the `phase` value, different account information and domain settings are used:

```json
"dev_account_number": "012345678910",
"dev_domain_name": "dev.domain.gov.uk",
"dev_domain_reference": "subdomain_dev",
"prod_account_number": "019876543210",
"prod_domain_name": "prod.domain.gov.uk",
"prod_domain_reference": "subdomain_prod"
```

The AWS region for data storage (S3 bucket, knowledge base localisation) is set by:

```json
"data_region": "eu-west-2"
```

### Domain Setup Requirement

**Important**: Before deploying EZComms, an AWS hosted domain must be set up separately within the account. EZComms uses this domain to:
1. Approve the identity required for email sending and receiving 
2. Configure the domain to act as an email exchange

The domain configuration is controlled by two critical parameters:

- **domain_name**: The base domain which you have access to the DNS settings for. If configured in AWS, EZComms will use DomainKeys Identified Mail (DKIM)-based domain verification to verify domain ownership without needing to provide DKIM authentication tokens manually.

- **domain_reference**: The configured MAIL FROM domain suitable for an identity. Messages you send through SES use a subdomain of amazonses.com as the default MAIL FROM domain. Setting the MAIL FROM to a domain you own enables you to comply with Domain-based Message Authentication, Reporting and Conformance (DMARC).

These `domain_name` and `domain_reference` values are a necessary requirement for EZComms to function properly. The domain specified in `dev_domain_name` or `prod_domain_name` must be properly configured in AWS Route 53 with appropriate MX records and verification settings. During deployment, EZComms will attempt to configure the necessary SES (Simple Email Service) settings for this domain.

## Core Infrastructure Configuration

### Storage Settings

These variables control the Athena database and S3 buckets for data storage:

```json
"athena_s3_bucket_data": "gds-idea-ezcomms",  // Base name for data bucket
"athena_database": "ezcomms",  // Athena database name
"athena_table_name_emails": "example_emails"  // Table for raw email content
"athena_workgroup": "DISABLED" // Query Athena tables
```

The actual bucket names will have the phase appended by default to avoid cross-account conflicts in S3 bucket deployment (e.g., `gds-idea-ezcomms-dev`). Please ensure you follow AWS naming conventions; S3 buckets cannot accept underscore characters, whilst we would suggest using underscores for Athena-based databases and tables to differentiate between storage variable names.

To enable querying of Athena tables, set `athena_workgroup` to `ENABLED`. By default, this is set to DISABLED to avoid incurring additional costs.

## Feature Toggles

EZComms uses several feature toggles to control which components are deployed:

### Email Infrastructure

```json
"deploy_emails_bucket": "false",  // Whether to create a new email bucket - only required on first deployment in an account
"s3_bucket_emailinbox": "gds-idea-emails",  // Base name for email bucket
"deploy_ses_infrastructure": "true",  // Whether to deploy SES infrastructure - sets up email handling and processing into base email Athena table
"deploy_ses_rules": "false",  // Whether to deploy SES rules - only required on first deployment in an account
"deploy_route53": "false"  // Whether to configure Route53 - only required on first deployment in an account
```

If `deploy_emails_bucket` is `false`, the system will use an existing bucket with the specified name set in "s3_bucket_emailinbox" on the assumption that the Simple Email Service ruleset has already been configured and is pointing at the expected S3 email bucket.
Be aware that if you are starting from scratch, you should set all toggles for email infrastructure to true - this ensures that the S3 email-receiving bucket is set up, the SES ruleset that sends email content to that S3 bucket is set up, and your AWS hosted domain and identity is configured with MX and TXT records required for email sending and receiving.
If you have previously used EZComms to deploy an SES ruleset/S3 email bucket, in a new instance of EZComms deployment, you should ensure that the s3_bucket_emailinbox is set to whatever the name of the S3 bucket is called that was created in the previous 

## Notification Settings

EZComms can set notifications for incoming emails:

```json
"deploy_sns_topic": "true",  // Whether to create an SNS topic
"sns_topic_name": "ezcomms_snstopic",  // Base name for SNS topic
"update_sns_subscription": "false",  // Whether to update SNS subscriptions (see)
"notification_email": [
  "jose.orjales@digital.cabinet-office.gov.uk"
]
```

This can be a single email address string or an array of addresses, and is a useful way of tracking when an email comes in that isn't tied to any one particular project. We strongly recommend you set this to be true and it can remain true without issue - the topic will only be updated with names if a new recipient is added.

### LLM Integration

```json
"deploy_llm": "true",  // Whether to deploy LLM-related stacks
"llm_region": "us-east-1",  // Region for LLM services - set this for the models you are interested in
"kb_id_exists": "false",  // Knowledge base ID (if exists)
"athena_table_name_responses": "example_responses"  // Table for LLM responses
```

The `kb_id_exists` variable is critical for LLM functionality. It must:
- Be alphanumeric
- Be 10 characters or less
- Reference an existing knowledge base ID after initial deployment

On first deployment, kb_id_exists should be set to false. This will avoid errors as the knowledge base must be created and the ID recorded in kb_id_exists before the LLM lambda function and models are able to use it.


### Email Sender

```json
"deploy_sender": "true",  // Whether to deploy email sender functionality
"sender_mode": "ses",  // Email sending method: "ses" or "notify"
"sender_subject": "DO NOT REPLY. Thank you for contacting the EZComms team.",  // Subject line (SES mode only)
"followup_email_address": "followup_email_here@support.gov.uk"  // Address for follow-ups
```

If wanting to integrate email sending, set deploy_sender to true. The system supports two email sending modes:

#### SES Mode (Amazon Simple Email Service)
```json
"sender_mode": "ses"
```

Uses AWS SES for email sending with custom HTML/text templates defined in your Lambda code. Required parameters:
- `sender_subject`: The email subject line
- `sender_email_address`: Constructed from `domain_reference` + `domain_name`

This mode requires:
- A verified domain in AWS SES
- Appropriate SES sending permissions
- Email templates defined in `lambda/sender/email_template.py`

#### Notify Mode (GOV.UK Notify)
```json
"sender_mode": "notify",
"notify_apikey_name": "ezcomms_notify_api_key",  // Name for the secret in AWS Secrets Manager
"notify_template_id": "your-template-id-from-notify"  // Template ID from GOV.UK Notify
```

Uses the GOV.UK Notify service for email sending with templates managed in the Notify dashboard. Required parameters:
- `notify_apikey_name`: Name for storing the API key in AWS Secrets Manager
- `notify_template_id`: The template ID from your GOV.UK Notify account

This mode requires:
- A GOV.UK Notify account (create at [notifications.service.gov.uk](https://www.notifications.service.gov.uk/))
- An API key from Notify (Team and whitelist key for testing, Live key for production)
- An email template in Notify with personalisation fields: `((question))` and `((response))`

**Setting the Notify API Key**: After deployment, you must manually set the API key in AWS Secrets Manager:
```bash
aws secretsmanager put-secret-value \
  --secret-id ezcomms_notify_api_key \
  --secret-string 'your-actual-api-key' \
  --region eu-west-2
```

We recommend you include in the subject header "DO NOT REPLY" and provide a separate follow-up email address for users who do not have their query answered, or who wish to get in touch with the team to discuss any data products or analysis shared automatically via the pipeline.
