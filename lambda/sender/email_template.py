def format_text_as_html_paragraphs(text):
    """
    Formats a block of text into HTML paragraphs for better readability.
    Splits the input text by double line breaks to identify paragraphs.
    Each paragraph is wrapped in <p> tags.
    Single line breaks within paragraphs are replaced with <br> tags to preserve formatting.

    Args:
        text (str): The input plain text to be formatted.

    Returns:
        str: The HTML-formatted string with paragraphs and line breaks.
    """
    paragraphs = text.split("\n\n")

    formatted_text = ""
    for para in paragraphs:
        if para.strip():
            para = para.replace("\n", "<br>")
            formatted_text += f"<p>{para}</p>"

    return formatted_text


def generate_email_template(query, response_text, email_support):
    """
    Generates both HTML and plain text versions of an email template based on a user query and an AI-generated response.

    Args:
        query (str): The user's original query.
        response_text (str): The AI-generated response text to the query.

    Returns:
        dict: A dictionary containing two keys:
            - 'html' (str): The formatted HTML version of the email.
            - 'text' (str): The plain text version of the email.
    """

    formatted_response = format_text_as_html_paragraphs(response_text)

    html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
                h1 {{ color: #2c3e50; }}
                h3 {{ color: #3498db; margin-bottom: 5px; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <h3>Thanks for getting in touch!</h3>
            <div class="response">{formatted_response}</div>
            <div class="footer">
                <p style="color: #7f8c8d;">The contents of this email are AI generated. If the response doesn't answer your question, email {email_support}</p>
                <p style="color: #7f8c8d;">Do not reply to this mailbox as it is not being monitored.</p>            
            </div>
        </body>
        </html>
        """

    text_content = f"""                    
        Response:
        {response_text}

        """
    return {"html": html_content, "text": text_content}
