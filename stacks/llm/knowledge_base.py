from typing import Any
from aws_cdk import CfnOutput, RemovalPolicy, Stack, Tags
from aws_cdk import aws_s3 as s3
from cdklabs.generative_ai_cdk_constructs import bedrock
from constructs import Construct


class DocumentKnowledgeBaseStack(Stack):
    """Creates a knowledge base for LLM processing using AWS Bedrock.

    This stack sets up the infrastructure for an AI knowledge base that can be used
    for answering questions based on documents. It creates:

    1. An S3 bucket for storing knowledge base documents
    2. A Bedrock Vector Knowledge Base for semantic processing
    3. A data source connector linking the S3 bucket to the knowledge base

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        project (str): The project name used for resource naming and tagging
        kb_name (str): Name for the knowledge base
        phase (str): Deployment phase (e.g., "dev", "prod")
        document_bucket (str): Name for the S3 bucket storing documents
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        docs_bucket: The S3 bucket for storing knowledge base documents
        kb: The Bedrock Vector Knowledge Base

    Output:
        {project}-KB-Output: The name of the knowledge base
        {project}-DocsBucket-Output: The name of the documents bucket
    """
    def __init__(
        self,
        scope: Construct,
        id: str,
        project: str,
        kb_name: str,
        phase: str,
        document_bucket: str,
        **kwargs: Any,
    ) -> None:
        description = f"Stack containing knowledge base configuration for {project}"
        super().__init__(scope, id, description=description, **kwargs)

        # Adding stack tags
        phase_tag = phase.capitalize()
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)

        # Create a new S3 bucket specifically for documents
        self.docs_bucket = s3.Bucket(
            self,
            f"{project}-DocumentsBucket",
            bucket_name=document_bucket,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Create a Knowledge Base
        self.kb = bedrock.VectorKnowledgeBase(
            self,
            f"{project}-KnowledgeBase",
            embeddings_model=bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
            name=kb_name,
            instruction="Use this knowledge base to answer questions based on the provided documents.",
        )

        # Link S3 data source for the knowledge base
        bedrock.S3DataSource(
            self,
            f"{project}-DocumentDataConnector",
            bucket=self.docs_bucket,
            knowledge_base=self.kb,
            data_source_name=f"{project}-documentstore",
            chunking_strategy=bedrock.ChunkingStrategy.SEMANTIC,
        )

        # Outputs
        CfnOutput(
            self,
            f"{project}-KB-Output",
            value=kb_name,
            description=f"{project} Knowledge Base Name",
        )

        CfnOutput(
            self,
            f"{project}-DocsBucket-Output",
            value=self.docs_bucket.bucket_name,
            description=f"Bucket for {project} documents",
        )
