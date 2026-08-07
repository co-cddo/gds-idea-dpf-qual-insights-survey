from typing import Any
from aws_cdk import (
    CfnOutput,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_glue as glue,
)
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct


class LLMStorageStack(Stack):
    """Creates the storage infrastructure for LLM responses.

    This stack sets up the Athena/Glue table for storing LLM responses. It references
    an existing S3 bucket and Athena database and creates a new table for responses.

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        project (str): The project name used for resource naming and tagging
        athena_database_name (str): The name of the Athena/Glue database
        athena_bucket_name_data (str): The name of the S3 bucket for Athena data
        responses_table_name (str): The name of the table for LLM responses
        phase (str, optional): Deployment phase (e.g., "dev", "prod"). Defaults to "dev".
        **kwargs: Additional arguments passed to the Stack constructor

    Attributes:
        athena_bucket: The referenced S3 bucket for Athena data
        response_table: The Glue table for storing LLM responses

    Output:
        LLM Database: The name of the Athena database
        ResponsesTable: The reference to the responses table in the Glue catalog
        ResponsesTableLocation: The S3 location for LLM responses data
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        project: str,
        athena_database_name: str,
        athena_bucket_name_data: str,
        responses_table_name: str,
        phase: str = "dev",
        **kwargs: Any,
    ) -> None:
        description = f"Athena database infrastructure for capturing and analysing email response data in the {project} pipeline"
        super().__init__(scope, id, description=description, **kwargs)

        # Adding general stack tags
        phase_tag = phase.capitalize()
        Tags.of(self).add("Project", project)
        Tags.of(self).add("Phase", phase_tag)
        Tags.of(self).add("Application", f"{project}-Database")

        # Get the name of the bucket where we're storing table data and information
        self.athena_bucket = s3.Bucket.from_bucket_name(
            self,
            f"{project}-ExistingAthenaBucketForLLMResponses",
            athena_bucket_name_data,
        )

        # Set up responses table to capture LLM responses ready to send information back
        self.response_table = glue.CfnTable(
            self,
            f"{project}-ResponsesTable",
            catalog_id=self.account,
            database_name=athena_database_name,
            table_input=glue.CfnTable.TableInputProperty(
                name=responses_table_name,
                storage_descriptor=glue.CfnTable.StorageDescriptorProperty(
                    columns=[
                        glue.CfnTable.ColumnProperty(
                            name="timestamp", type="timestamp"
                        ),
                        glue.CfnTable.ColumnProperty(name="unique_id", type="string"),
                        glue.CfnTable.ColumnProperty(name="user_email", type="string"),
                        glue.CfnTable.ColumnProperty(
                            name="email_content", type="string"
                        ),
                        glue.CfnTable.ColumnProperty(name="llm_context", type="string"),
                        glue.CfnTable.ColumnProperty(
                            name="llm_response", type="string"
                        ),
                    ],
                    location=f"s3://{self.athena_bucket.bucket_name}/{responses_table_name}/",
                    input_format="org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                    output_format="org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                    serde_info=glue.CfnTable.SerdeInfoProperty(
                        serialization_library="org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                        parameters={
                            "parquet.compression": "SNAPPY",
                            "serialization.format": "1",
                        },
                    ),
                ),
                table_type="EXTERNAL_TABLE",
                parameters={
                    "classification": "parquet",
                    "parquet.compress": "SNAPPY",
                    "EXTERNAL": "TRUE",
                },
            ),
        )
        Tags.of(self.response_table).add("ResourceType", "Table")
        Tags.of(self.response_table).add("Service", "Glue")

        CfnOutput(
            self,
            "LLM Database",
            value=athena_database_name,
            description="Database name",
        )

        CfnOutput(
            self,
            "ResponsesTable",
            value=self.response_table.ref,
            description="LLM Responses table",
        )

        CfnOutput(
            self,
            "ResponsesTableLocation",
            value=f"s3://{athena_bucket_name_data}/{responses_table_name}/",
            description="S3 location for LLM responses data",
        )
