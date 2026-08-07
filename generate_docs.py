#!/usr/bin/env python3
"""
Script to generate MkDocs documentation structure for EZComms CDK stacks.
"""

import os


def create_directory(path):
    """Create directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created directory: {path}")


def create_file(path, content):
    """Create file with content if it doesn't exist."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(content)
        print(f"Created file: {path}")
    else:
        print(f"File already exists: {path}")


def main():
    """Main function to create the documentation structure."""
    # Create base directories
    base_dirs = [
        "docs",
        "docs/architecture",
        "docs/reference",
        "docs/reference/incoming",
        "docs/reference/llm",
        "docs/reference/outgoing",
        "docs/guides",
    ]

    for directory in base_dirs:
        create_directory(directory)

    # Create template files for architecture
    create_file(
        "docs/architecture/overview.md",
        "# Architecture Overview\n\nDescribe the overall architecture of the EZComms system here.",
    )

    # Create template files for guides
    create_file(
        "docs/guides/deployment.md",
        "# Deployment Guide\n\nInstructions for deploying the EZComms system.",
    )
    create_file(
        "docs/guides/configuration.md",
        "# Configuration Guide\n\nInstructions for configuring the EZComms system.",
    )

    # Create template files for stacks
    stack_templates = {
        "docs/reference/storage.md": """# Storage Stack

::: stacks.storage.StorageStack
""",
        "docs/reference/app.md": """# Main Application

Overview of the main application that puts together all the stacks.

```python
# Example of how the app is initialized
app = cdk.App()
```

Reference documentation for the main application module.
""",
        "docs/reference/incoming/ses_infra.md": """# SES Infrastructure Stack

::: stacks.incoming.ses_infra.SESEmailsStack
""",
        "docs/reference/incoming/ses_layer.md": """# SES Layer Stack

::: stacks.incoming.ses_layer.EmailLayerStack
""",
        "docs/reference/incoming/ses_s3.md": """# SES S3 Stack

::: stacks.incoming.ses_s3.S3EmailsStack
""",
        "docs/reference/incoming/ses_sns.md": """# SES SNS Stack

::: stacks.incoming.ses_sns.SNSEmailsStack
""",
        "docs/reference/llm/knowledge_base.md": """# Knowledge Base Stack

::: stacks.llm.knowledge_base.DocumentKnowledgeBaseStack
""",
        "docs/reference/llm/llm_image.md": """# LLM Docker Image Stack

::: stacks.llm.llm_image.LLMDockerImageStack
""",
        "docs/reference/llm/llm_lambda.md": """# LLM Lambda Functions Stack

::: stacks.llm.llm_lambda.LLMLambdaFunctionsStack
""",
        "docs/reference/llm/llm_storage.md": """# LLM Storage Stack

::: stacks.llm.llm_storage.LLMStorageStack
""",
        "docs/reference/outgoing/outgoing_lambda.md": """# Outgoing Lambda Functions Stack

::: stacks.outgoing.outgoing_lambda.OutgoingLambdaFunctionsStack
""",
        "docs/reference/outgoing/sender_image.md": """# Sender Docker Image Stack

::: stacks.outgoing.sender_image.SenderDockerImageStack
""",
    }

    for path, content in stack_templates.items():
        create_file(path, content)

    print("\nDocumentation structure created successfully!")
    print("You can now build your documentation with: mkdocs build")
    print("Or serve it locally with: mkdocs serve")


if __name__ == "__main__":
    main()
