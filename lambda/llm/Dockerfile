# Use the official AWS Lambda Python 3.12 base image. Specify platform or it'll generate as if on a Mac architecture.
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install dependencies individually in a specific order as Mirascope/Pydantic requires Cython which fails typical load otherwise with pip install -r requirements.txt
RUN pip install --no-cache-dir Cython
RUN pip install --no-cache-dir pydantic
RUN pip install --no-cache-dir boto3
RUN pip install --no-cache-dir pandas
RUN pip install --no-cache-dir awswrangler
RUN pip install --no-cache-dir "mirascope[bedrock]>=1.22.1"

# Copy the Lambda handler code into the container
COPY index.py .
COPY src/ src/

# Set the CMD to your handler (module.function)
CMD ["index.handler"]