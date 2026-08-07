# Use the official AWS Lambda Python 3.12 base image. Specify platform or it'll generate as if on a Mac architecture.
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Copy the requirements file and install dependencies
COPY requirements.txt . 
RUN pip install -r requirements.txt

# Copy the Lambda handler code into the container
COPY index.py .
COPY email_template.py .

# Set the CMD to your handler (module.function)
CMD ["index.handler"]