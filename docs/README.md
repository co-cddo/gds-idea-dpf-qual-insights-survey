![EZComms Architecture Diagram](ezcomms.png)

# EZComms

EZComms is a standardised, modular AWS infrastructure solution for email processing pipelines. It streamlines the deployment and management of systems that receive, process, and respond to emails at scale using AWS services and AI capabilities.

## Key Features

- **Automated Email Reception**: Configure AWS SES to receive emails and store them securely in S3
- **Structured Data Storage**: Parse and store email content in Athena/Glue tables for efficient querying
- **AI-Powered Analysis**: Process email content using AWS Bedrock foundation models with knowledge base integration
- **Automated Responses**: Generate and send contextually relevant email responses via Amazon SES or GOV.UK Notify
- **Modular Architecture**: Deploy only the components you need with feature toggles
- **Environment Flexibility**: Support for both development and production environments

## Prerequisites

### System Requirements

- **Python**: Version 3.13 or greater
  ```bash
  python --version  # Should show 3.13.x or higher
  ```

- **UV Package Manager**: For dependency management
  ```bash
  pip install uv  # Install UV if not already available
  ```

- **Docker**: Required for building Lambda container images
  ```bash
  docker --version  # Verify Docker is installed and running
  ```

- **AWS CDK**: Version 2.154.1 or later
  ```bash
  npm install -g aws-cdk  # Install CDK globally
  cdk --version           # Verify CDK version
  ```

### AWS Account Configuration

- **AWS CLI**: Configured with appropriate credentials using standard AWS credential management
  ```bash
  aws configure  # Set up your AWS credentials if not already configured
  ```

- **IAM Permissions**: Ensure your AWS account/user has permissions for:
  - CloudFormation stack creation and management
  - S3 bucket creation and management
  - Lambda function creation
  - SES configuration
  - Glue/Athena database and table creation
  - Bedrock model access (if using LLM features)
  - IAM role creation
  - ECR image pushing
  - AWS Secrets Manager (if using GOV.UK Notify)

- **AWS Hosted Domain**: A domain in Route 53 for handling emails
  - The domain must be registered and managed within AWS
  - Administrative access to configure domain settings

- **Foundation Model Access**: If using LLM features, ensure:
  - You have approved access to foundation models in AWS Bedrock
  - Appropriate service quotas are set for model usage
  - Knowledge base creation permissions are granted

- **GOV.UK Notify Account (Optional)**
If using GOV.UK Notify for email sending (sender_mode: "notify"):

- GOV.UK Notify Account: Create an account at notifications.service.gov.uk
- API Key: Generate an API key from your Notify account:
  - Use a Team and whitelist key for testing (limits sending to team members only)
  - Use a Live key for production (allows sending to any email address)
- Email Template: Create an email template in your Notify account with these personalisation fields initially (these can be changed later to match your expected contents from the LLM):

((question)) - The user's original query
((response)) - The LLM-generated response
- Template ID: Note the template ID from Notify (found in the template URL settings after creation) to use in cdk.json configuration

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/co-cddo/gds-idea-ezcomms.git
   cd gds-idea-ezcomms
   ```

2. **Set up the development environment**:
   ```bash
   uv sync        # Synchronise dependencies using the existing .venv
   source .venv/bin/activate # Activate virtual environment (Unix/Mac)
   # OR
   .\.venv\Scripts\activate  # Activate virtual environment (Windows)
   ```

3. **Adding new functionality** (if needed):
   ```bash
   uv add package_name  # Add new package to dependencies
   ```

4. **Configure AWS environment**:
   ```bash
   aws configure    # Set up your AWS credentials if not already configured
   cdk bootstrap    # Bootstrap your AWS environment for CDK
   ```

5. **Update deployment configuration** in `cdk.json` based on your requirements.

## Usage

EZComms provides a modular architecture for building email processing pipelines:

### Storing emails in a structured way

The Incoming/Archivist component captures incoming emails from SES, stores them in S3, and catalogues them in Athena tables:

1. Configure SES to receive emails for your domain
2. Set up email routing rules to store messages in S3
3. Configure notification preferences for incoming emails
4. Process email content into structured Athena tables

### Processing emails to extract contents using an LLM

The LLM component/Reviewer processes email content against a knowledge base:

1. Create and populate a knowledge base with relevant documents
2. Configure the LLM processing pipeline to analyse incoming emails
3. Store analysis results in structured tables

### Responding back to emails using LLM

The Outgoing/Writer component sends automated responses:

1. Configure email templates with appropriate branding and formatting
  - Amazon SES: Use AWS-native email service with HTML/text templates
  - GOV.UK Notify: Use the GOV.UK service with managed templates
2. Configure email templates with appropriate branding and formatting
3. Set up email sending rules and permissions
4. Establish feedback mechanisms for recipients

## Project Layout

    app.py         # Main CDK application entry point
    cdk.json       # CDK deployment configuration
    stacks/        # CDK stack definitions for infrastructure
    lambda/        # Lambda functions for processing
    docs/          # Documentation files