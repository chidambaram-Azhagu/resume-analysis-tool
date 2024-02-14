import streamlit as st
import google.generativeai as genai
import os
import json
import PyPDF2 as pdf
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
import ast
import pandas as pd
import re
import boto3
from urllib.parse import urlparse
from io import BytesIO

load_dotenv() ## load all our environment variables

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

#Function to extract the response and to make as python dictionary for 'Percentage Match'.
def extract_percentage_match_info(response):
    try:
        response_info = {}
        percentage_match = re.search(r'^([^%]+%)', response)
        if percentage_match:
            response_info['percentage_match'] = percentage_match.group(1).strip()

        keywords_missing_match = re.search(r'Keywords Missing: (.*?)Final Thoughts:', response, re.DOTALL)
        if keywords_missing_match:
            response_info['keywords_missing'] = keywords_missing_match.group(1).strip()

        final_thoughts_match = re.search(r'Final Thoughts: (.+)', response)
        if final_thoughts_match:
            response_info['final_thoughts'] = final_thoughts_match.group(1).strip()
        return response_info
    except Exception as e:
        print("Error in extract_percentage_match_info()", e)

# Function to extract the response and to make as python dictionary for 'Fit for Role'.
def extract_fit_for_role_response_info(response):
    try:
        response_info = {}
        match = re.search(r'(Yes|No)', response)
        if match:
            response_info['is_relatable'] = match.group(1)

        remaining_content = response[match.end():].strip()
        if remaining_content:
            remaining_content = remaining_content.lstrip(', ')
            if remaining_content[0].isalpha():
                remaining_content = remaining_content.capitalize()
            elif remaining_content[0] in ['.', ' ']:
                remaining_content = remaining_content.lstrip('. ')
                remaining_content = remaining_content.capitalize()
            response_info['reason'] = remaining_content

        return response_info
    except Exception as e:
        print("Error in extract_fit_for_role_response_info() ", e)

#Function to Get Gemini Response:
def get_gemini_response(job_description, pdf_content, prompt):
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content([prompt, job_description, pdf_content])
        return response.text
    except Exception as e:
        print("Error in get_gemini_response() ", e)

#Function to Get Gemini Response for summary:
def get_gemini_response_summary(prompt, pdf_content):
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content([prompt, pdf_content])
        return response.text
    except Exception as e:
        print("Error in get_gemini_response_summary() ", e)

# Function to extract text from the uploaded resume (PDF format):
def input_pdf_text(uploaded_file):
    try:
        reader = pdf.PdfReader(uploaded_file)
        text = ""
        for page in range(len(reader.pages)):
            page = reader.pages[page]
            text += str(page.extract_text())
        return text
    except Exception as e:
        print("Error in input_pdf_text() ", e)

# Function to check whether the response is 'Positive' or 'Negative' for filter purpose:
def get_gemini_response_filter(input):
    try: 
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content([input])
        return response.text
    except Exception as e:
        print("Error in get_gemini_response_filter() ", e)

# Function to extract bucket name and object key from S3 URL
def parse_s3_url(s3_url):
    try:
        parsed_url = urlparse(s3_url)
        bucket_name = parsed_url.netloc.split('.')[0]
        object_key = parsed_url.path.lstrip('/')
        return bucket_name, object_key
    except Exception as e:
        print("Error in parse_s3_url() ->", e)

# Function to download file from S3
def download_file_from_s3(bucket_name, object_key, file_path):
    try:
        s3 = boto3.client('s3')
        s3.download_file(bucket_name, object_key, file_path)
        return True
    except Exception as e:
        print("Error downloading file from S3:", e)
        return False

# Function to process S3 URL input
def process_s3_input(s3_url):
    try:
        bucket_name, object_key = parse_s3_url(s3_url)
        temp_folder = "temp"
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)
        file_path = os.path.join(temp_folder, os.path.basename(object_key))
        if download_file_from_s3(bucket_name, object_key, file_path):
            return temp_folder
        else:
            print("Failed to download file from S3.")
            return None
    except Exception as e:
        print("Error processing S3 input:", e)


## streamlit app UI datas :
def main():
    st.markdown("""
    <style>
        .st-emotion-cache-16txtl3 {
            padding: 1rem 1.5rem;
        }
    </style>
    """, unsafe_allow_html=True)
    with st.sidebar:
            st.title("Resume:")
            selection = st.selectbox("Choose file selection method:", ["Choose Files", "S3 Url"])
            uploaded_files = None  
            if selection == "Choose Files":
                uploaded_files = st.file_uploader("Upload Resume(s)", type="pdf", accept_multiple_files=True, help="Please upload the pdf")
            elif selection == "S3 Url":
                s3_url = st.text_input("Enter the URL to the S3 object (file):")
                if s3_url:
                    file_folder_name = process_s3_input(s3_url)
                    if file_folder_name:
                        if os.path.isdir(file_folder_name):
                            folder_files = [os.path.join(file_folder_name, filename) for filename in os.listdir(file_folder_name) if filename.endswith('.pdf')]
                            uploaded_files = [open(file, 'rb') for file in folder_files]
                    else:
                        st.write("Failed to download file from S3. Please check the URL.")
                        uploaded_files = None
            num_uploaded_files = len(uploaded_files) if uploaded_files else 0
            st.write(f"Total PDF's Uploaded: {num_uploaded_files}")
            if num_uploaded_files > 0:
                summary_button = st.button("Summary of the Resumes")
                percent_match_button = st.button("Percentage Match")
                fit_button = st.button("Fit for Role")
                filter_button = st.button("Filter")
            else:
                summary_button = st.button("Summary of the Resumes", disabled=True)
                percent_match_button = st.button("Percentage Match", disabled=True)
                fit_button = st.button("Fit for Role", disabled=True)
                filter_button = st.button("Filter", disabled=True)

            #Prompts passed to the Gemini AI:
            summary_prompt = """
            You are an experienced Technical Human Resource Manager, your task is to review the provided resume 
            and give only the summary of the resume in very short like their skills, current position,
            if he/she is studying give as a fresher, give response like that and build a context about the candidate with in 5 lines .

            """

            percentage_match_prompt = """
            You are a skilled ATS (Applicant Tracking System) scanner with a deep understanding of data science and ATS functionality, 
            your task is to evaluate the "RESUME DATA" against the provided "JOB DESCRIPTION". give me the percentage of match if the "RESUME DATA" matches
            the "JOB DESCRIPTION". First, the output should come as a percentage (Give Just percentage with percentage symbol, no need of any words), then keywords missing (use 'Keywords Missing: ' keyword) for this give the missed values from "JOB DESCRIPTION" by comparing with "RESUME DATA" if missed give the missed values, if nothing is missed then give 'None' for 'Keywords Missing:', and lastly, final thoughts (use 'Final Thoughts: ' keyword) in a short manner.
            """

            filter_prompt = """
            Below I have given you the 1)"JOB DESCRIPTION" and 2) "RESUME DATA". I want you to compare whether the "RESUME DATA" is more or less relatable for the given "JOB DESCRIPTION".
            If the "RESUME DATA" is relatable to provided "JOB DESCRIPTION", just give the reason for relatable in very short.  
            """

            fit_for_role_prompt = """
            Below I have given you the 1)"JOB DESCRIPTION" and 2) "RESUME DATA". I want you to compare whether the "RESUME DATA" is Relatable for the given "JOB DESCRIPTION"
            and if the "RESUME DATA" is relatable to provided "JOB DESCRIPTION", Just say 'Yes' or 'No' and the reason for Yes/No. 
            """

    #logic 
    if summary_button or percent_match_button or fit_button:
        if summary_button:  # Only execute if "Submit 1" button is clicked
            results = []
            if not uploaded_files:
                st.write("Please upload at least one resume")
            else:
                def process_file(uploaded_file):
                    try:
                        pdf_content = input_pdf_text(uploaded_file)
                        response = get_gemini_response_summary(summary_prompt, pdf_content)
                        if selection == "S3 Url" :
                            results.append({"File Name":os.path.basename(uploaded_file.name),"Response": response})
                        else :
                            results.append({"File Name": uploaded_file.name, "Response": response})
                    except Exception as e :
                        print('err in summary_button data',e)

                # Use ThreadPoolExecutor for parallel processing
                with ThreadPoolExecutor() as executor:
                    executor.map(process_file, uploaded_files)
                st.subheader("Responses:")
                # st.table(results)
                df = pd.DataFrame(results, columns=["File Name", "Response"])
                df.index = range(1, len(df) + 1)
                df.index.name = 'Sl.No'
                st.write(df) 
        elif percent_match_button or fit_button:  # For "percent_match" or "fit" Button
            if not input_text:
                st.write("Please provide the Job Description")
            elif not uploaded_files:
                st.write("Please upload at least one resume")
            else:
                results = []
                def process_file(uploaded_file):
                    try:
                        pdf_content = input_pdf_text(uploaded_file)
                        pdf_content_to_ai = '"RESUME DATA": \n' + pdf_content
                        if not fit_button:  
                            response = get_gemini_response(processed_input_text, pdf_content_to_ai, percentage_match_prompt)
                            response_as_dictionary = extract_percentage_match_info(response)
                            if selection == "S3 Url" :
                                results.append({"File Name":os.path.basename(uploaded_file.name), "Percentage Match": response_as_dictionary["percentage_match"], "Keywords Missing": response_as_dictionary["keywords_missing"], "Final Thoughts": response_as_dictionary["final_thoughts"]})
                            else:
                                results.append({"File Name": uploaded_file.name, "Percentage Match": response_as_dictionary["percentage_match"], "Keywords Missing": response_as_dictionary["keywords_missing"], "Final Thoughts": response_as_dictionary["final_thoughts"]})
                        else :
                            response = get_gemini_response(processed_input_text, pdf_content_to_ai, fit_for_role_prompt)
                            response_as_dictionary = extract_fit_for_role_response_info(response)
                            if selection == "S3 Url" :
                                results.append({"File Name":os.path.basename(uploaded_file.name), "Status": response_as_dictionary["is_relatable"], "Reason" : response_as_dictionary["reason"]})
                            else:
                                results.append({"File Name": uploaded_file.name, "Status": response_as_dictionary["is_relatable"], "Reason" : response_as_dictionary["reason"]})
                    except Exception as e :
                        print('Error in submit data',e)

                # Use ThreadPoolExecutor for parallel processing
                with ThreadPoolExecutor() as executor:
                    executor.map(process_file, uploaded_files)
                st.subheader("Responses:")
                # st.table(results)
                if percent_match_button:
                    df = pd.DataFrame(results, columns=["File Name", "Percentage Match", "Keywords Missing", "Final Thoughts"])
                else:
                    df = pd.DataFrame(results, columns=["File Name", "Status", "Reason"])
                df.index = range(1, len(df) + 1)
                df.index.name = 'Sl.No'
                st.write(df)
    elif filter_button:
        if not input_text:
            st.write("Please provide the Job Description")
        elif not uploaded_files:
            st.write("Please upload at least one resume")
        else:
            results = []
            def process_filter_file(uploaded_file):
                try:
                    pdf_content = input_pdf_text(uploaded_file)
                    pdf_content_to_ai = '"RESUME DATA": \n' + pdf_content
                    response = get_gemini_response(processed_input_text, pdf_content_to_ai, fit_for_role_prompt)
                    response_as_dictionary = extract_fit_for_role_response_info(response)
                    # check_response = get_gemini_response_filter("check whether the content is positive (like 'is relatable' or 'is more relatable' or 'is more or less relatable') or negative (like  'is not relatable' or 'is less relatable') if positive return 'Positive' else return 'Negative' " + response)
                    if selection == "S3 Url" :
                        if response_as_dictionary["is_relatable"] == 'Yes':
                            results.append({"File Name":os.path.basename(uploaded_file.name), "Reason" : response_as_dictionary["reason"]})
                    else:
                        if response_as_dictionary["is_relatable"] == 'Yes':
                            results.append({"File Name": uploaded_file.name, "Reason" : response_as_dictionary["reason"]})
                except Exception as e :
                    print('Error in submit filter', e)
            with ThreadPoolExecutor() as executor:
                executor.map(process_filter_file, uploaded_files)
            # Displaying results in a table
            if results:
                st.subheader("Total Responses: " + str(len(results)))
                df = pd.DataFrame(results, columns=["File Name", "Reason"])
                df.index = range(1, len(df) + 1)
                df.index.name = 'Sl.No'
                st.write(df) 
            else:
                st.subheader("Oops... No data found")

uploaded_files = None
st.set_page_config(page_title="Smart Resume Analyzing", layout='centered')
st.title("Smart Resume Analyzing")
input_text = st.text_area("Job Description: ", key="input")
processed_input_text = '"JOB DESCRIPTION": ' + input_text
# uploaded_files = st.file_uploader("Upload Resume(s)", type="pdf", accept_multiple_files=True, help="Please upload the pdf")

if uploaded_files:
    st.write(f"{len(uploaded_files)} PDFs Uploaded Successfully")


if __name__ == "__main__":
    main()