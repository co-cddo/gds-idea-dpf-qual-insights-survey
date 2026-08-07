from typing import List, Optional

import boto3
from mirascope import BaseMessageParam
from mirascope.core import bedrock
from pydantic import BaseModel, Field


# Define a response model for an expanded query to improve knowledge base responses
class ExpandedQuery(BaseModel):
    expanded_query: str = Field(
        description="An expanded version of the user's query that includes relevant keywords and concepts to improve retrieval"
    )


# Define a response model for the answers
class Answer(BaseModel):
    answer: str = Field(description="The answer to the user's question")
    sources: List[str] = Field(
        description="Sources of information used to generate the answer"
    )


class LLMAgent:
    def __init__(
        self,
        llm_region: str,
        kb_region: str,
        kb_id: str,
        profile_name: Optional[str] = None,
    ):
        """
        Initialise the LLM Agent with optional AWS profile and region settings.

        Args:
            profile_name: AWS profile name to use, defaults to None (default profile)
            llm_region: Region for Bedrock Runtime for LLM calls, defaults to us-east-1
            kb_region: Region for Bedrock Agent Runtime (Knowledge Base), defaults to eu-west-2
        """
        # Set up the session and clients based on provided parameters
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
        else:
            session = boto3.Session()

        self.client = session.client("bedrock-runtime", region_name=llm_region)
        self.kb_client = session.client("bedrock-agent-runtime", region_name=kb_region)

        # Initialise the LLM functions with the appropriate clients
        self._setup_llm_functions()

    def _setup_llm_functions(self):
        """Set up the LLM functions with the current clients."""

        @bedrock.call(
            "us.anthropic.claude-3-5-haiku-20241022-v1:0",
            call_params={
                "temperature": 0.1,
                "max_tokens": 300,
            },
            client=self.client,
            response_model=ExpandedQuery,
        )
        def expand_query(query: str) -> List[BaseMessageParam]:
            return [
                BaseMessageParam(
                    role="system",
                    content="""You are an expert at improving search queries for retrieval systems. 
                                
                    Your task is to expand the user's query to improve document retrieval by:
                    1. Including relevant synonyms and related concepts
                    2. Breaking down abstract queries into more specific searchable terms
                    3. Phrasing the query in multiple ways that might match how information is expressed in documents
                    4. Adding technical terminology that might appear in formal documentation

                    Keep your expansion focused and relevant to the core information need. The goal is to improve semantic retrieval without drifting from the original intent.

                    Return ONLY the expanded query without any explanation or commentary.""",
                ),
                BaseMessageParam(
                    role="user",
                    content=f"Original query: {query}\n\nPlease expand this query to improve document retrieval.",
                ),
            ]

        @bedrock.call(
            "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            call_params={
                "temperature": 0.3,
            },
            client=self.client,
            response_model=Answer,
        )
        def answer_query_with_context(messages: List[BaseMessageParam]) -> Answer:
            return messages

        # Assign the functions to the instance
        self.expand_query = expand_query
        self.answer_query_with_context = answer_query_with_context

    def query_knowledge_base(self, query: str, kb_id: str, max_results: int = 5) -> str:
        """
        Query the knowledge base with an expanded version of the user query.

        Args:
            query: The original user query
            kb_id: Knowledge base ID to query
            max_results: Maximum number of results to return

        Returns:
            Concatenated context from the knowledge base
        """
        expanded = self.expand_query(query)
        expanded_query = expanded.expanded_query

        print(f"Original query: {query}")
        print(f"Expanded query: {expanded_query}")

        # Use the expanded query for retrieval
        response = self.kb_client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": expanded_query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        # Extract and format retrieved content
        retrieved_results = []
        for result in response["retrievalResults"]:
            content = result["content"]["text"]
            retrieved_results.append(content)

        return "\n\n".join(retrieved_results)

    def create_rag_messages(
        self, username: str, query: str, context: str
    ) -> List[BaseMessageParam]:
        """
        Create RAG messages for the LLM to answer the query.

        Args:
            username: User's name for personalization
            query: The original user query
            context: Retrieved context from knowledge base

        Returns:
            List of messages for the LLM
        """
        return [
            BaseMessageParam(
                role="system",
                content=f"""You are AImy, a helpful assistant for responding to emails. You're responding to {username}, so always address them by name in a friendly, professional tone.

            Your responses should be:
            1. Personalised - Always begin with their name (e.g., "Hello {username}," or "{username},")
            2. Concise - Clear and to the point
            3. Helpful - Provide direct, actionable information
            4. Professional - Maintain a warm but professional tone
            5. Structured - Use bullet points for lists or steps

            Important guidelines:
            - Include any relevant links or URLs that appear in the context
            - DO NOT mention "retrieved context," "provided information," or similar phrases
            - If you don't have enough information to answer, be honest but helpful
            - Present information as your own knowledge rather than citing sources
            - Always include complete URLs when they appear in the context
            """,
            ),
            BaseMessageParam(
                role="user",
                content=f"""Question: {query}

            Context:
            {context}

            Please answer the question for {username}.
            """,
            ),
        ]

    def answer_with_rag(
        self, username: str, query: str, kb_id: str, max_results: int = 5
    ) -> Answer:
        """
        End-to-end RAG pipeline: expand query, retrieve context, and answer.

        Args:
            username: User's name for personalisation
            query: The original user query
            kb_id: Knowledge base ID to query
            max_results: Maximum number of results to return

        Returns:
            Structured answer with sources
        """
        # First retrieve the relevant information
        context = self.query_knowledge_base(query, kb_id, max_results)

        # Create the messages with the retrieved context and username
        messages = self.create_rag_messages(username, query, context)

        # Call the LLM with the RAG-enhanced messages
        response = self.answer_query_with_context(messages)

        return response
