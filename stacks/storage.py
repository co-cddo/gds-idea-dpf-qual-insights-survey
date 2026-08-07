from typing import Any
from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_glue as glue,
)
from aws_cdk import (
    aws_athena as athena
)
from aws_cdk import (
    aws_s3 as s3,
)
from constructs import Construct


class StorageStack(Stack):
    """Creates the core storage infrastructure for EZComms email processing.

    This stack sets up the foundational data storage components for storing and
    analyzing email data. It creates:

    1. An S3 bucket for storing Athena query results and associated data
    2. A Glue database for organizing email data tables
    3. A Glue table for storing email content with a standardized schema

    The table is configured to use Parquet format with SNAPPY compression for
    optimal query performance and storage efficiency.

    Args:
        scope (Construct): The parent AWS CDK construct
        id (str): The construct ID for this stack
        project (str): The project name used for resource naming and tagging
        athena_database_name (str): The name for the Athena/Glue database
        athena_bucket_name (str): The name for the S3 bucket storing Athena data
        emails_table_name (str): The table name for storing captured emails
        phase (str, optional): Deployment phase (e.g., "dev", "prod"). Defaults to "dev".
        **kwargs: Additional arguments passed to the Stack constructor (i.e. data storage environment)

    Output:
        AthenaDatabase: The name of the created Athena/Glue database
        AthenaDataBucket: The name of the S3 bucket for Athena data
        EmailsTable: The reference to the emails table in the Glue catalog
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        project: str,
        athena_database_name: str,
        athena_bucket_name: str,
        emails_table_name: str,
        athena_workgroup: str,
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

        # Create S3-based Athena bucket for holding all project-specific data
        self.athena_bucket = s3.Bucket(
            self,
            f"{project}-AthenaDataBucket",
            bucket_name=athena_bucket_name,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            event_bridge_enabled=True,
        )
        print(f"Created new bucket: {athena_bucket_name}")
        Tags.of(self.athena_bucket).add("ResourceType", "Storage")
        Tags.of(self.athena_bucket).add("Service", "S3")

        # Create Glue Database and Table
        self.database = glue.CfnDatabase(
            self,
            f"{project}-AthenaDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=athena_database_name
            ),
        )
        Tags.of(self.database).add("ResourceType", "Database")
        Tags.of(self.database).add("Service", "Glue")

        # Set up example table for capturing generic emails
        self.email_table = glue.CfnTable(
            self,
            f"{project}-QueriesTable",
            catalog_id=self.account,
            database_name=self.database.ref,
            table_input=glue.CfnTable.TableInputProperty(
                name=emails_table_name,
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
                    ],
                    location=f"s3://{self.athena_bucket.bucket_name}/{emails_table_name}/",
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
        Tags.of(self.email_table).add("ResourceType", "Table")
        Tags.of(self.email_table).add("Service", "Glue")

        # Set up Athena workgroup - Default is set to DISABLED, just replace with ENABLED in cdk.json
        if athena_workgroup.upper() != "DISABLED":
            self.workgroup = athena.CfnWorkGroup(
                self,
                f"{project}-AthenaWorkGroup",
                name=f"{project}-WorkGroup",
                description=f"Workgroup for {project} Athena queries",
                state="ENABLED",  # If we're creating it, it should be enabled
                work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                    result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                        output_location=f"s3://{self.athena_bucket.bucket_name}/query-results/",
                    ),                                                                  
                ),
                recursive_delete_option=True,
            )
            Tags.of(self.workgroup).add("ResourceType", "Analytics")
            Tags.of(self.workgroup).add("Service", "Athena")
            
            # Workgroup Output if enabled
            CfnOutput(
                self, 
                "AthenaWorkgroup",
                value=self.workgroup.name,
                description="Athena workgroup name",
            )
        else:
            self.workgroup = None

        # Outputs
        CfnOutput(
            self,
            "AthenaDatabase",
            value=self.database.ref,
            description="Athena database name",
        )

        CfnOutput(
            self,
            "AthenaDataBucket",
            value=self.athena_bucket.bucket_name,
            description="Bucket for Athena data and query results",
        )

        CfnOutput(
            self,
            "EmailsTable",
            value=self.email_table.ref,
            description="Email responses source table",
        )
