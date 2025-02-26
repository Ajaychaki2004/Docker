import jwt
import json
from datetime import datetime, timedelta, timezone
from django.http import JsonResponse
from bson import ObjectId
from pymongo import MongoClient
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from rest_framework import status
import base64
from bson.errors import InvalidId
import re  # Add this import for regex
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pytesseract
import cv2
import numpy as np
import google.generativeai as genai
from PIL import Image, ImageEnhance, ImageFilter

# Create your views here.
JWT_SECRET = "secret"
JWT_ALGORITHM = "HS256"


def generate_tokens(admin_user):
    """
    Generate tokens for authentication. Modify this with JWT implementation if needed.
    """
    access_payload = {
        'admin_user': str(admin_user),
        'role':'admin',
        "exp": datetime.utcnow() + timedelta(days=1),
        "iat": datetime.utcnow(),
    }

    # Encode the token
    token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {'jwt': token}

def generate_tokens_superadmin(superadmin_user):
    """
    Generate tokens for authentication. Modify this with JWT implementation if needed.
    """
    access_payload = {
        'superadmin_user': str(superadmin_user),
        'role':'superadmin',
        "exp": datetime.utcnow() + timedelta(days=1),
        "iat": datetime.utcnow(),
    }

    # Encode the token
    token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"jwt": token}


# MongoDB connection
client = MongoClient('mongodb+srv://ihub:ihub@cce.ksniz.mongodb.net/')
db = client['CCE']
admin_collection = db['admin']
internship_collection = db['internships']
job_collection = db['jobs']
achievement_collection = db['achievement']
superadmin_collection = db['superadmin']
student_collection = db['students']
reviews_collection = db['reviews']
study_material_collection = db['studyMaterial']
contactus_collection = db["contact_us"]
student_achievement_collection=db["student_achievement"]
message_collection = db["message"]

# Dictionary to track failed login attempts
failed_login_attempts = {}
lockout_duration = timedelta(minutes=2)  # Time to lock out after 3 failed attempts

# Function to check if the password is strong
def is_strong_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must include at least one digit."
    if not re.search(r"[@$!%*?&#]", password):
        return False, "Password must include at least one special character."
    return True, ""

# Function to send confirmation email
def send_confirmation_email(to_email, name, password):
    subject = "Admin Account Created"
    body = f"""
    Your admin account has been successfully created on the CCE platform.
    Username: {name}
    Password: {password}
    Please keep your credentials safe and secure.
    """

    msg = MIMEMultipart()
    msg['From'] = settings.EMAIL_HOST_USER
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to the Gmail SMTP server
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        server.starttls()  # Secure the connection
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)  # Login with credentials
        text = msg.as_string()
        server.sendmail(settings.EMAIL_HOST_USER, to_email, text)  # Send the email
        server.quit()  # Close the connection
        print(f"Confirmation email sent to {to_email}")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

@csrf_exempt
def admin_signup(request):
    if request.method == "POST":
        try:
            # Parse the request payload
            data = json.loads(request.body)
            name = data.get('name')
            email = data.get('email')
            password = data.get('password')
            department = data.get('department')  # New field
            college_name = data.get('college_name')  # New field

            # Validate required fields
            if not all([name, email, password, department, college_name]):
                return JsonResponse({'error': 'All fields are required'}, status=400)

            # Check if the email already exists
            if admin_collection.find_one({'email': email}):
                return JsonResponse({'error': 'This email is already assigned to an admin'}, status=400)

            # Check if the password is strong
            is_valid, error_message = is_strong_password(password)
            if not is_valid:
                return JsonResponse({'error': error_message}, status=400)

            # Hash the password
            hashed_password = make_password(password)

            # Create the admin user document
            admin_user = {
                'name': name,
                'email': email,
                'password': hashed_password,
                'department': department,  # Store department
                'college_name': college_name,  # Store college name
                'status': 'Active',  # Default status is Active
                'created_at': datetime.now(),  # Store account creation date
                'last_login': None  # Initially, no last login
            }

            # Insert the document into the collection
            admin_collection.insert_one(admin_user)

            # Send confirmation email with username and password
            send_confirmation_email(email, name, password)

            return JsonResponse({'message': 'Admin user created successfully, confirmation email sent.'}, status=201)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def generate_reset_token(length=6):
    return ''.join(random.choices(string.digits, k=length))
 
@csrf_exempt
def admin_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            email = data.get("email")
            password = data.get("password")

            # Check if the email contains "sns"
            if "@sns" not in email:
                return JsonResponse({'error': 'Email must contain domain id'}, status=400)

            # Check lockout status
            if email in failed_login_attempts:
                lockout_data = failed_login_attempts[email]
                if lockout_data['count'] >= 3 and datetime.now() < lockout_data['lockout_until']:
                    return JsonResponse({'error': 'Too many failed attempts. Please try again after 2 minutes.'}, status=403)

            # Find the admin user by email
            admin_user = admin_collection.find_one({'email': email})

            if admin_user is None:
                return JsonResponse({'error': 'Account not found with this email id'}, status=404)

            # Check if the account is Active
            if not admin_user.get('status', 'Active') == 'Active':
                return JsonResponse({'error': 'Admin account is deactivated. Please contact support.'}, status=403)

            if check_password(password, admin_user['password']):
                # Clear failed attempts after successful login
                failed_login_attempts.pop(email, None)

                # Generate JWT token
                admin_id = admin_user.get('_id')
                tokens = generate_tokens(admin_id)

                # Update last login timestamp
                admin_collection.update_one({'email': email}, {'$set': {'last_login': datetime.now()}})

                # Set the username in cookies
                response = JsonResponse({'username': admin_user['name'], 'tokens': tokens, 'last_login': datetime.now()}, status=200)

                return response
            else:
                # Track failed attempts
                if email not in failed_login_attempts:
                    failed_login_attempts[email] = {'count': 1, 'lockout_until': None}
                else:
                    failed_login_attempts[email]['count'] += 1
                    if failed_login_attempts[email]['count'] >= 3:
                        failed_login_attempts[email]['lockout_until'] = datetime.now() + lockout_duration

                return JsonResponse({'error': 'Invalid email or password.'}, status=401)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)

# def generate_reset_token(length=4):
#     # return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
#     return ''.join(random.choices(string.digits, k=length))

@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    try:
        email = request.data.get('email')
        user = admin_collection.find_one({"email": email})
        if not user:
            return Response({"error": "Email not found"}, status=400)
        
        reset_token = generate_reset_token()
        expiration_time = datetime.utcnow() + timedelta(hours=1)
        
        admin_collection.update_one(
            {"email": email},
            {"$set": {"password_reset_token": reset_token, "password_reset_expires": expiration_time}}
        )
        
        send_mail(
            'Password Reset Request',
            f'Use this token to reset your password: {reset_token}',
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
        
        return Response({"message": "Password reset token sent to your email"}, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp(request):
    try:
        email = request.data.get('email')
        otp = request.data.get('otp')
        
        user = admin_collection.find_one({"email": email})
        if not user:
            return Response({"error": "User not found"}, status=404)
        
        if user.get("password_reset_token") != otp:
            return Response({"error": "Invalid OTP"}, status=400)
        
        if user.get("password_reset_expires") < datetime.utcnow():
            return Response({"error": "OTP has expired"}, status=400)
        
        return Response({"message": "verification successfully"}, status=200)
    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
from django.contrib.auth.hashers import make_password

@csrf_exempt
def reset_password(request):
    """Reset Password Function"""
    if request.method == 'POST':
        try:
            # Parse the request payload
            data = json.loads(request.body)
            email = data.get('email')
            new_password = data.get('newPassword')

            # Validate the request data
            if not email or not new_password:
                return JsonResponse({"error": "Email and new password are required."}, status=400)

            # Fetch the user by email
            user = admin_collection.find_one({"email": email})
            if not user:
                return JsonResponse({"error": "User not found."}, status=404)

            # Hash the new password
            hashed_password = make_password(new_password)

            # Ensure hashed password starts with "pbkdf2_sha256$"
            if not hashed_password.startswith("pbkdf2_sha256$"):
                return JsonResponse({"error": "Failed to hash the password correctly."}, status=500)

            # Update the password in MongoDB
            result = admin_collection.update_one(
                {"email": email},
                {"$set": {
                    "password": hashed_password,
                    "password_reset_token": None,  # Clear reset token
                    "password_reset_expires": None  # Clear expiration time
                }}
            )

            if result.modified_count == 0:
                return JsonResponse({"error": "Failed to update the password in MongoDB."}, status=500)

            return JsonResponse({"message": "Password reset successfully"}, status=200)

        except Exception as e:
            return JsonResponse({"error": f"An error occurred: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request method. Use POST."}, status=405)

@csrf_exempt
def get_admin_list(request):
    try:
        # Fetch all documents from the admin_collection
        admins = admin_collection.find()
        admin_list = []

        for admin in admins:
            admin["_id"] = str(admin["_id"])  # Convert ObjectId to string
            admin_list.append(admin)

        return JsonResponse({"admins": admin_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def admin_details(request, id):
    if request.method == 'GET':
        try:
            admin = admin_collection.find_one({'_id': ObjectId(id)})
            if not admin:
                return JsonResponse({'error': 'Admin not found'}, status=404)

            admin['_id'] = str(admin['_id'])

            last_login = admin.get('last_login')
            last_login = last_login.strftime('%Y-%m-%d %H:%M:%S') if last_login else "Never logged in"

            admin_data = {
                '_id': admin['_id'],
                'name': admin.get('name', 'N/A'),
                'email': admin.get('email', 'N/A'),
                'status': admin.get('status', 'Active'),
                'department': admin.get('department', 'N/A'),
                'college_name': admin.get('college_name', 'N/A'),
                'created_at': datetime.now(),
                'last_login': last_login
            }

            # Fetch jobs posted by this admin
            jobs = job_collection.find({'admin_id': str(admin['_id'])})
            jobs_list = []
            for job in jobs:
                job['_id'] = str(job['_id'])
                job_data = job.get('job_data', {})
                job_data['_id'] = job['_id']
                job_data['updated_at'] = job.get('updated_at', "N/A")  # Include updated_at field
                jobs_list.append(job_data)

            # Fetch internships posted by this admin
            internships = internship_collection.find({'admin_id': str(admin['_id'])})
            internships_list = []
            for internship in internships:
                internship['_id'] = str(internship['_id'])
                internship_data = internship.get('internship_data', {})
                internship_data['_id'] = internship['_id']
                internship_data['updated_at'] = internship.get('updated_at', "N/A")
                internships_list.append(internship_data)

            # Fetch achievements posted by this admin
            achievements = achievement_collection.find({'admin_id': str(admin['_id'])})
            achievements_list = []
            for achievement in achievements:
                achievement['_id'] = str(achievement['_id'])
                achievements_list.append(achievement)

            return JsonResponse({'admin': admin_data, 'jobs': jobs_list, 'internships': internships_list, 'achievements': achievements_list}, status=200)

        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
@csrf_exempt
def edit_admin_details(request, id):
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            admin = admin_collection.find_one({'_id': ObjectId(id)})
            if not admin:
                return JsonResponse({'error': 'Admin not found'}, status=404)

            # Update fields if provided in the request
            if 'name' in data:
                admin['name'] = data['name']
            if 'email' in data:
                admin['email'] = data['email']
            if 'status' in data:
                admin['status'] = data['status']
            if 'department' in data:
                admin['department'] = data['department']
            if 'college_name' in data:
                admin['college_name'] = data['college_name']

            # Save the updated admin details back to the database
            admin_collection.update_one({'_id': ObjectId(id)}, {'$set': admin})

            return JsonResponse({'success': 'Admin details updated successfully'}, status=200)

        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def admin_status_update(request, id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_status = data.get("status")

            if new_status not in ["Active", "Inactive"]:
                return JsonResponse({'error': 'Invalid status value'}, status=400)

            update_result = admin_collection.update_one({'_id': ObjectId(id)}, {'$set': {'status': new_status}})

            if update_result.matched_count == 0:
                return JsonResponse({'error': 'Admin not found'}, status=404)

            return JsonResponse({'message': f'Admin status updated to {new_status}'}, status=200)

        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    
@csrf_exempt
def super_admin_signup(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            name = data.get("name")
            email = data.get("email")
            password = data.get("password")

            # Check if the email contains "sns"
            if "@sns" not in email:
                return JsonResponse(
                    {"error": "Email must contain domain id"}, status=400
                )

            # Check if the email already exists
            if superadmin_collection.find_one({'email': email}):
                return JsonResponse({'error': 'Super admin user with this email already exists'}, status=400)

            # Check if the password is strong
            if not re.match(
                r"^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$", password
            ):
                return JsonResponse(
                    {
                        "error": "Password must be at least 8 characters long, contain an uppercase letter, a number, and a special character"
                    },
                    status=400,
                )

            # Hash the password
            password = make_password(password)

            # Create the super admin user document
            super_admin_user = {
                'name': name,
                'email': email,
                'password': password,
            }

            # Insert the document into the collection
            superadmin_collection.insert_one(super_admin_user)

            return JsonResponse({'message': 'Super admin user created successfully'}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

@csrf_exempt
def super_admin_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            email = data.get("email")
            password = data.get("password")

            # Check if the email contains "sns"
            if "@sns" not in email:
                return JsonResponse({'error': 'Email must contain domain id'}, status=400)

            # Check lockout status
            if email in failed_login_attempts:
                lockout_data = failed_login_attempts[email]
                if lockout_data['count'] >= 3 and datetime.now() < lockout_data['lockout_until']:
                    return JsonResponse({'error': 'Too many failed attempts. Please try again after 2 minutes.'}, status=403)

            # Find the super admin user by email
            super_admin_user = superadmin_collection.find_one({'email': email})

            if super_admin_user is None:
                return JsonResponse({'error': 'Account not found with this email id'}, status=404)

            if check_password(password, super_admin_user['password']):
                # Clear failed attempts after successful login
                failed_login_attempts.pop(email, None)

                # Generate JWT token
                super_admin_id = super_admin_user.get('_id')
                tokens = generate_tokens_superadmin(super_admin_id)
                return JsonResponse({'username': super_admin_user['name'], 'tokens': tokens}, status=200)
            else:
                # Track failed attempts
                if email not in failed_login_attempts:
                    failed_login_attempts[email] = {'count': 1, 'lockout_until': None}
                else:
                    failed_login_attempts[email]['count'] += 1
                    if failed_login_attempts[email]['count'] >= 3:
                        failed_login_attempts[email]['lockout_until'] = datetime.now() + lockout_duration

                return JsonResponse({'error': 'Invalid email or password.'}, status=401)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    
# ============================================================== JOBS ======================================================================================
#  Configure Gemini API
genai.configure(api_key="AIzaSyCLDQgKnO55UQrnFsL2d79fxanIn_AL0WA")

# Configure Tesseract (Ensure Tesseract is installed)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def preprocess_image(image):
    """Preprocesses the image for better OCR accuracy."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)  # Binarization
    return thresh

def extract_text_from_image(image_path):
    """Extracts text by splitting the image into 4 parts and merging results."""
    image = cv2.imread(image_path)  # Load image
    processed_image = preprocess_image(image)  # Preprocess

    height, width = processed_image.shape
    parts = [
        processed_image[0:height//2, 0:width//2],  # Top Left
        processed_image[0:height//2, width//2:width],  # Top Right
        processed_image[height//2:height, 0:width//2],  # Bottom Left
        processed_image[height//2:height, width//2:width],  # Bottom Right
    ]

    extracted_text = []
    
    for i, part in enumerate(parts):
        text = pytesseract.image_to_string(part, lang="eng")  # OCR on each part
        extracted_text.append(text.strip())

    return "\n".join(extracted_text)  # Merge extracted texts

def analyze_text_with_gemini_api(ocr_text):

    """Processes extracted text into a structured paragraph before extracting job details in JSON format."""

    # Step 1: Generate Structured Paragraph from OCR Text
    initial_prompt = f"""
    You are an AI assistant specializing in job data extraction.
    Convert the following unstructured job posting text into a structured, well-formatted paragraph.
    The paragraph should be organized into subtopics like **Job Title, Company, Description, Responsibilities, Skills, Education, Experience, Salary, Benefits, Work Type, and Application Process**.

    **Unstructured Job Posting:**  
    {ocr_text}

    **Example Output Format:**  
    **Job Title:** [Extracted or 'No Data Available']  
    **Company:** [Extracted or 'No Data Available']  
    **Description:** [Extracted or 'No Data Available']  
    **Responsibilities:**  
    - Responsibility 1  
    - Responsibility 2 (Infer if missing)  
    **Required Skills:**  
    - Skill 1  
    - Skill 2 (Infer if missing)  
    **Education:** [Extracted Qualification or 'No Data Available']  
    **Experience:** [Years of experience required or 'No Data Available']  
    **Salary:** [Extracted salary or 'No Data Available']  
    **Benefits:**  
    - Benefit 1  
    - Benefit 2 (Infer if missing)  
    **Work Type:** [Full-time/Part-time/Remote]  
    **Application Process:** [Extracted Process or 'No Data Available']  

    Ensure the output is well-structured and formatted properly.
    """

    # Call Gemini AI Model
    model = genai.GenerativeModel("gemini-1.5-flash-8b")
    structured_paragraph = model.generate_content(initial_prompt).text


    main_prompt = f"""
    Extract job posting details from the following structured text and return the output in a strict JSON format.

    **Structured Job Posting:**  
    {structured_paragraph}


    **Output Format (Ensure All Fields Exist & Fill Missing Ones)**:
    {{
        "title": "Extracted Job Title or 'No Data Available'",
        "company_name": "Extracted Company Name or 'No Data Available'",
        "company_overview": "Extracted or 'No Data Available'",
        "company_website": "Extracted Website or 'No Data Available'",
        "job_description": "Extracted Job Description or 'No Data Available'",
        "key_responsibilities": [
            "Responsibility 1",
            "Responsibility 2",
            "Infer if missing"
        ],
        "required_skills": [
            "Skill 1",
            "Skill 2",
            "Infer if missing"
        ],
        "education_requirements": "Extracted Qualification or 'No Data Available'",
        "experience_level": "Years of experience required or 'No Data Available'",
        "salary_range": "Extracted salary or 'No Data Available'",
        "benefits": [
            "Benefit 1",
            "Benefit 2",
            "Infer if missing"
        ],
        "job_location": "Extracted location or 'No Data Available'",
        "work_type": "Full-time/Part-time (Infer from job type)",
        "application_instructions": "Extracted Application Process or 'No Data Available'",
        "application_deadline": "YYYY-MM-DD or 'No Data Available'",
        "contact_email": "Extracted email or 'No Data Available'",
        "contact_phone": ["Extracted phone number or 'No Data Available'"],
        "job_link": "Extracted job link or 'No Data Available'",
        "selectedCategory": "Job Category (Infer from job type)",
        "selectedWorkType": "On-site/Remote"
    }}

    **Ensure output is valid JSON with no additional text.**
"""
    # Generate structured job details JSON
    response = model.generate_content(main_prompt).text

    # Ensure response contains JSON
    try:
        # **Clean AI response (remove Markdown formatting)**
        cleaned_response = re.sub(r"```json|```", "", response.text).strip()
        json_output = json.loads(cleaned_response)  # Convert to JSON

        # Ensure all required fields have values (fallback to "No Data Available")
        required_fields = {
            "title": "No Data Available",
            "company_name": "No Data Available",
            "job_link": "No Data Available",
            "contact_email": "No Data Available",
            "contact_phone": ["No Data Available"]
        }

        for key, default_value in required_fields.items():
            if key not in json_output or not json_output[key]:
                json_output[key] = default_value

        return json_output

    except json.JSONDecodeError as e:
        return {"error": "AI processing failed. Please try again."}

@csrf_exempt
def upload_job_image(request):
    """Handles job image uploads, extracts text using OCR, and refines it using AI."""
    if request.method == "POST":
        try:
            job_image = request.FILES.get("image")
            if not job_image:
                return JsonResponse({"error": "No image provided"}, status=400)

            # Step 1: Extract raw text
            raw_text = extract_text_from_image(Image.open(job_image)) 

            # Step 2: Process AI enhancement
            job_data = analyze_text_with_gemini_api(raw_text)

            if "error" in job_data:
                return JsonResponse({"error": "AI processing failed. Please try again."}, status=500)

            return JsonResponse({"message": "Text extracted successfully", "data": job_data}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)
    
@csrf_exempt
def job_post(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.POST.get('data', '{}'))  # Extracting JSON data
            image = request.FILES.get('image')
            
            role = data.get('role')
            userid = data.get('userId')
            auto_approval_setting = superadmin_collection.find_one({"key": "auto_approval"})
            is_auto_approval = auto_approval_setting.get("value", False) if auto_approval_setting else False
            is_publish = True if role == 'superadmin' or (role == 'admin' and is_auto_approval) else None
            
            application_deadline_str = data.get('application_deadline')
            if not application_deadline_str:
                return JsonResponse({"error": "Missing required field: application_deadline"}, status=400)
            
            try:
                application_deadline = datetime.strptime(application_deadline_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return JsonResponse({"error": "Invalid date format for application_deadline. Use YYYY-MM-DD."}, status=400)
            
            now = datetime.now(timezone.utc)
            current_status = "Active" if application_deadline >= now else "Expired"
            
            required_fields = ['title', 'job_link', 'application_deadline', 'company_name']
            for field in required_fields:
                if field not in data:
                    return JsonResponse({"error": f"Missing required field: {field}"}, status=400)
            
            # Convert image to Base64 if provided
            image_base64 = None
            if image:
                image_base64 = base64.b64encode(image.read()).decode('utf-8')
            
            job_post = {
                "job_data": {
                    "title": data['title'],
                    "company_name": data['company_name'],
                    "company_overview": data.get('company_overview', "NA"),
                    "company_website": data.get('company_website', "NA"),
                    "job_description": data.get('job_description', "NA"),
                    "key_responsibilities": data.get('key_responsibilities', "NA"),
                    "required_skills": data.get('required_skills', ""),
                    "education_requirements": data.get('education_requirements', "NA"),
                    "experience_level": data.get('experience_level', "NA"),
                    "salary_range": data.get('salary_range', "NA"),
                    "benefits": data.get('benefits', "NA"),
                    "job_location": data.get('job_location', "NA"),
                    "work_type": data.get('work_type', "NA"),
                    "work_schedule": data.get('work_schedule', "NA"),
                    "application_instructions": data.get('application_instructions', "NA"),
                    "application_deadline": application_deadline,
                    "contact_email": data.get('contact_email', "NA"),
                    "contact_phone": data.get('contact_phone', "NA"),
                    "job_link": data['job_link'],
                    "selectedCategory": data.get('selectedCategory', "NA"),
                    "selectedWorkType": data.get('selectedWorkType', "NA"),
                    "image": image_base64  # Storing image as Base64
                },
                "admin_id" if role == "admin" else "superadmin_id": userid,
                "is_publish": is_publish,
                "status": current_status,
                "updated_at": datetime.now(timezone.utc)
            }
            
            job_collection.insert_one(job_post)
            return JsonResponse({"message": "Job posted successfully, awaiting approval."}, status=200)
        
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method. Only POST is allowed."}, status=405)


@csrf_exempt
@api_view(["POST"])
def test_job_post(request):
    try:
        data = json.loads(request.body)

        role = data.get('role')
        print(role)
        auto_approval_setting = superadmin_collection.find_one({"key": "auto_approval"})
        is_auto_approval = auto_approval_setting.get("value", False) if auto_approval_setting else False

        is_publish = None  # Default: Pending (null)
        userid = data.get('userId')

        if not userid:
            return Response({"error": "Userid not found"}, status=status.HTTP_401_UNAUTHORIZED)

        if role == 'admin':
            if is_auto_approval:
                is_publish = True  # Auto-approve enabled, mark as approved

        elif role == 'superadmin':
            is_publish = True  # Superadmin posts are always approved

        # Replace null values with 'N/A'
        def replace_nulls(d):
            for k, v in d.items():
                if isinstance(v, dict):
                    replace_nulls(v)
                elif v is None:
                    d[k] = 'N/A'
                elif isinstance(v, list):
                    for i in range(len(v)):
                        if v[i] is None:
                            v[i] = 'N/A'
            return d

        data = replace_nulls(data)
        # Remove unnecessary fields
        data.pop('role', None)
        data.pop('userId', None)

        # Prepare job data
        job_post = {
            "job_data": data,
            "admin_id" if role == "admin" else "superadmin_id": userid,  # Save the admin_id from the token
            "is_publish": is_publish,  # Auto-approve if enabled
            "status": "Active" if data.get('Application_Process_Timeline', {}).get('Application_Deadline', 'N/A') >= datetime.now().isoformat() else "expired",
            "updated_at": datetime.now()
        }

        # Insert the job post into the database
        test_job_collection = db['Testjob']
        test_job_collection.insert_one(job_post)

        return Response(
            {
                "message": "Job stored successfully",
                "auto_approved": is_auto_approval
            },
            status=status.HTTP_201_CREATED
        )
    except Exception as e:
        print(e)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


        
@csrf_exempt
def get_jobs_for_mail(request):
    try:
        jobs = job_collection.find()
        job_list = []

        for job in jobs:
            job["_id"] = str(job["_id"])  # Convert ObjectId to string

            # Convert is_publish to readable status
            approval_status = "Waiting for Approval" if job.get("is_publish") is None else (
                "Approved" if job["is_publish"] else "Rejected"
            )

            # Fetch admin details using admin_id
            admin_id = job.get("admin_id")
            admin_name = "Super Admin"
            if admin_id:
                admin = admin_collection.find_one({"_id": ObjectId(admin_id)})
                if admin:
                    admin_name = admin.get("name", "Super Admin")

            # Ensure job_data exists and has application_deadline
            if "job_data" in job and "application_deadline" in job["job_data"]:
                deadline = job["job_data"]["application_deadline"]
                if deadline:
                    if isinstance(deadline, datetime):
                        # If deadline is already a datetime object, format it directly
                        formatted_deadline = deadline.strftime("%Y-%m-%d")
                    elif isinstance(deadline, str):
                        try:
                            # Try parsing full datetime format
                            formatted_deadline = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%d")
                        except ValueError:
                            try:
                                # If the first format fails, try the plain date format
                                formatted_deadline = datetime.strptime(deadline, "%Y-%m-%d").strftime("%Y-%m-%d")
                            except ValueError:
                                # If neither format works, keep it as is (to avoid crashes)
                                formatted_deadline = deadline
                    else:
                        formatted_deadline = str(deadline)  # Fallback to string conversion

                    job["job_data"]["application_deadline"] = formatted_deadline  # Update formatted value

            # Add human-readable approval status and admin name
            job["approval_status"] = approval_status
            job["admin_name"] = admin_name  # Attach admin name

            job_list.append(job)

        return JsonResponse({"jobs": job_list}, status=200, safe=False)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
 
@csrf_exempt
@api_view(["POST"])
def toggle_auto_approval(request):
    """
    API to enable or disable auto-approval.
    """
    try:
        data = json.loads(request.body)
        is_auto_approval = data.get("is_auto_approval", False)  # Default is False

        # Save or update the setting in MongoDB
        superadmin_collection.update_one(
            {"key": "auto_approval"},
            {"$set": {"value": is_auto_approval}},
            upsert=True
        )

        return JsonResponse({"message": "Auto-approval setting updated successfully"}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
@api_view(["GET"])
def get_auto_approval_status(request):
    """
    API to check if auto-approval is enabled.
    """
    try:
        auto_approval_setting = superadmin_collection.find_one({"key": "auto_approval"})
        is_auto_approval = auto_approval_setting.get("value", False) if auto_approval_setting else False
        return JsonResponse({"is_auto_approval": is_auto_approval}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def review_job(request, job_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            action = data.get("action")
            if action not in ["approve", "reject"]:
                return JsonResponse({"error": "Invalid action"}, status=400)
            job = job_collection.find_one({"_id": ObjectId(job_id)})
            if not job:
                return JsonResponse({"error": "Job not found"}, status=404)
            if action == "approve":
                job_collection.update_one(
                    {"_id": ObjectId(job_id)},
                    {
                        "$set": {
                            "is_publish": True,
                            "updated_at": datetime.now(),
                        }
                    },
                )
                return JsonResponse(
                    {"message": "Job approved and published successfully"}, status=200
                )
            elif action == "reject":
                job_collection.update_one(
                    {"_id": ObjectId(job_id)},
                    {
                        "$set": {
                            "is_publish": False,
                            "updated_at": datetime.now(),
                        }
                    },
                )
                return JsonResponse(
                    {"message": "Job rejected successfully"}, status=200
                )
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)
    
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def get_published_jobs(request):
    """
    Fetch all jobs with is_publish set to True (Approved).
    """
    try:
        job_list = []
        published_jobs = job_collection.find({"is_publish": True})  # Ensures only approved jobs are fetched
        for job in published_jobs:
            job["_id"] = str(job["_id"])  # Convert ObjectId to string
            # Rename 'job_location' to 'location' if it exists
            if "job_data" in job and "job_location" in job["job_data"]:
                job["job_data"]["location"] = job["job_data"].pop("job_location")
            # Calculate total views
            total_views = sum(view["count"] for view in job.get("views", []))
            # Remove views field and add total_views
            job.pop("views", None)
            job["total_views"] = total_views
            job_list.append(job)
        return JsonResponse({"jobs": job_list}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    
@csrf_exempt
def get_job_by_id(request, job_id):
    """
    Fetch a single job by its ID.
    """
    try:
        job = job_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            return JsonResponse({"error": "Job not found"}, status=404)

        job["_id"] = str(job["_id"])  # Convert ObjectId to string
        return JsonResponse({"job": job}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def update_job(request, job_id):
    """
    Update a job by its ID.
    """
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)

            # Convert job_id to ObjectId
            job_object_id = ObjectId(job_id)

            # Find the existing job
            job = job_collection.find_one({"_id": job_object_id})
            if not job:
                return JsonResponse({"error": "Job not found"}, status=404)

            # Ensure _id is not modified
            data.pop('_id', None)

            # Add or update the 'edited' field
            data['edited'] = data.get('edited', True)  # Default to True if not provided

            # Update the job document
            job_collection.update_one({"_id": job_object_id}, {"$set": data})

            # Fetch updated job and convert ObjectId fields to strings
            updated_job = job_collection.find_one({"_id": job_object_id})
            updated_job["_id"] = str(updated_job["_id"])

            # Ensure all ObjectId fields (like admin_id, item_id) are converted to strings
            if "admin_id" in updated_job and isinstance(updated_job["admin_id"], ObjectId):
                updated_job["admin_id"] = str(updated_job["admin_id"])
            if "item_id" in updated_job and isinstance(updated_job["item_id"], ObjectId):
                updated_job["item_id"] = str(updated_job["item_id"])

            return JsonResponse({"job": updated_job}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def delete_job(request, job_id):
    """
    Delete a job by its ID and remove it from students' saved jobs.
    """
    if request.method == 'DELETE':
        try:
            # Check if the job exists
            job = job_collection.find_one({"_id": ObjectId(job_id)})
            if not job:
                return JsonResponse({"error": "Job not found"}, status=404)

            # Delete the job from the job collection
            job_collection.delete_one({"_id": ObjectId(job_id)})

            # Update students' saved jobs
             # Update students' saved jobs
            student_collection.update_many(
                {"saved_jobs": job_id},
                {"$pull": {"saved_jobs": job_id}}
            )

            # Update students' applied jobs
            student_collection.update_many(
                {"applied_jobs.job_id": job_id},
                {"$pull": {"applied_jobs": {"job_id": job_id}}}
            )

            return JsonResponse({"message": "Job deleted successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def get_all_jobs_and_internships(request):
    """
    Fetch all jobs and internships and return their statistics.
    """
    try:
        # Fetch all jobs
        jobs = list(job_collection.find())
        total_jobs = len(jobs)
        job_pending_requests = sum(1 for job in jobs if job.get("is_publish") is None)  # Fixed logic
        job_rejected_count = sum(1 for job in jobs if job.get("is_publish") is False)  # Now correctly counts rejections

        for job in jobs:
            job["_id"] = str(job["_id"])  # Convert ObjectId to string
            # Rename 'job_location' to 'location' if it exists
            if "job_data" in job and "job_location" in job["job_data"]:
                job["job_data"]["location"] = job["job_data"].pop("job_location")
            # Calculate total views for jobs
            total_views = sum(view["count"] for view in job.get("views", []))
            job.pop("views", None)
            job["total_views"] = total_views

        # Fetch all internships
        internships = list(internship_collection.find())
        total_internships = len(internships)
        internship_pending_requests = sum(1 for internship in internships if internship.get("is_publish") is None)  # Fixed logic
        internship_rejected_count = sum(1 for internship in internships if internship.get("is_publish") is False)  # Now correctly counts rejections

        for internship in internships:
            internship["_id"] = str(internship["_id"])  # Convert ObjectId to string
            # Calculate total views for internships
            total_views = sum(view["count"] for view in internship.get("views", []))
            internship.pop("views", None)
            internship["total_views"] = total_views

        # Calculate total pending and rejected counts
        pending_requests = job_pending_requests + internship_pending_requests
        rejected_count = job_rejected_count + internship_rejected_count

        return JsonResponse({
            "jobs": jobs,
            "internships": internships,
            "total_jobs": total_jobs,
            "total_internships": total_internships,
            "pending_requests": pending_requests,
            "rejected_count": rejected_count
        }, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ============================================================== ACHIEVEMENTS ======================================================================================

@csrf_exempt
@api_view(['POST'])
def post_achievement(request):
    try:
        # Decode the JWT token
        role = request.POST.get("role")
        print(role)
        userid = request.POST.get("userId")
          # Extract admin_id from token
        if not userid:
            return Response({"error": "user_id not found"}, status=status.HTTP_401_UNAUTHORIZED)

        # Get text data from request
        name = request.POST.get("name")
        achievement_description = request.POST.get("achievement_description")  # Corrected field name
        achievement_type = request.POST.get("achievement_type")
        company_name = request.POST.get("company_name")
        date_of_achievement = request.POST.get("date_of_achievement")
        batch = request.POST.get("batch")

        # Check if an image was uploaded
        if "photo" in request.FILES:
            image_file = request.FILES["photo"]
            # Convert the image to base64
            image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        else:
            image_base64 = None  # Photo is optional

        # Prepare the document to insert
        achievement_data = {
            "name": name,
            "achievement_description": achievement_description,  # Corrected field name
            "achievement_type": achievement_type,
            "company_name": company_name,
            "date_of_achievement": date_of_achievement,
            "batch": batch,
            "photo": image_base64,  # Store as base64
            "admin_id": userid,  # Save the admin_id from the token
            "created_by": role,
            "is_publish": True,  # Directly publish as no approval needed
            "updated_at": datetime.now()
        }

        # Insert into MongoDB
        achievement_collection.insert_one(achievement_data)

        return Response({"message": "Achievement stored successfully"}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
def manage_achievements(request):
    if request.method == 'GET':
        # Retrieve JWT token from Authorization Header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({'error': 'No token provided'}, status=401)
        
        jwt_token = auth_header.split(" ")[1]
        
        try:
            # Decode JWT token
            decoded_token = jwt.decode(jwt_token, JWT_SECRET, algorithms=["HS256"])
            role = decoded_token.get('role')
            admin_user = decoded_token.get('admin_user') if role == "admin" else decoded_token.get('superadmin_user')
            
            if not admin_user:
                return JsonResponse({"error": "Invalid token"}, status=401)
            
            # Fetch achievements from MongoDB based on admin_user
            achievements = achievement_collection.find({"admin_id": admin_user} if role == "admin" else {})
            achievement_list = [{**achievement, "_id": str(achievement["_id"])} for achievement in achievements]
            
            return JsonResponse({"achievements": achievement_list}, status=200)
        
        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'JWT token has expired'}, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({'error': f'Invalid JWT token: {str(e)}'}, status=401)
        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
@csrf_exempt
def update_achievement(request, achievement_id):
    """
    Update an achievement by its ID, including image updates.
    """
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            achievement = achievement_collection.find_one({"_id": ObjectId(achievement_id)})

            if not achievement:
                return JsonResponse({"error": "Achievement not found"}, status=404)

            # Remove _id if present in the update data
            if '_id' in data:
                del data['_id']

            # Check if an image was uploaded (optional)
            if "photo" in request.FILES:
                image_file = request.FILES["photo"]
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
                data["photo"] = image_base64  # Store the updated image as base64

            # Update the achievement in MongoDB
            data["updated_at"] = datetime.now()  # Update timestamp
            achievement_collection.update_one({"_id": ObjectId(achievement_id)}, {"$set": data})

            # Fetch updated achievement
            updated_achievement = achievement_collection.find_one({"_id": ObjectId(achievement_id)})
            updated_achievement["_id"] = str(updated_achievement["_id"])  # Convert ObjectId to string

            return JsonResponse({"achievement": updated_achievement}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)
    
@csrf_exempt
def get_achievements(request):
    try:
        achievements = achievement_collection.find()
        achievement_list = [
            {**achievement, "_id": str(achievement["_id"])}  # Convert ObjectId to string
            for achievement in achievements
        ]
        return JsonResponse({"achievements": achievement_list}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def get_achievement_by_id(request, achievement_id):
    """
    Fetch a single achievement by its ID.
    """
    try:
        achievement = achievement_collection.find_one({"_id": ObjectId(achievement_id)})
        if not achievement:
            return JsonResponse({"error": "Achievement not found"}, status=404)

        achievement["_id"] = str(achievement["_id"])  # Convert ObjectId to string
        return JsonResponse({"achievement": achievement}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

@csrf_exempt
def delete_achievement(request, achievement_id):
    """
    Delete an achievement by its ID.
    """
    if request.method == 'DELETE':
        try:
            result = achievement_collection.delete_one({"_id": ObjectId(achievement_id)})

            if result.deleted_count == 0:
                return JsonResponse({"error": "Achievement not found"}, status=404)

            return JsonResponse({"message": "Achievement deleted successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def get_published_achievements(request):
    try:
        published_achievements = achievement_collection.find({"is_publish": True})
        achievement_list = [
            {**achievement, "_id": str(achievement["_id"])}  # Convert ObjectId to string
            for achievement in published_achievements
        ]
        return JsonResponse({"achievements": achievement_list}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
# ============================================================== INTERNSHIP ======================================================================================
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

@csrf_exempt
def upload_internship_image(request):
    if request.method == "POST":
        try:
            # Get uploaded image
            internship_image = request.FILES.get("image")
            if not internship_image:
                return JsonResponse({"error": "No image provided"}, status=400)

            # Open and process image
            image = Image.open(internship_image)
            extracted_text = pytesseract.image_to_string(image, lang="eng")

            # Preprocess text and map to fields
            internship_data = parse_internship_details(extracted_text)

            return JsonResponse({"message": "Text extracted successfully", "data": internship_data}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method"}, status=405)

# Function to parse text and map it to internship form fields
def parse_internship_details(text):
    # Remove unwanted characters and normalize text
    text = re.sub(r"\n+", "\n", text).strip()

    # Extract key information using regex or keyword matching
    title = extract_field(text, ["Position", "Title"])
    company_name = extract_field(text, ["Company Name", "Organization"])
    location = extract_field(text, ["Location"], default="Remote")
    duration = extract_field(text, ["Duration"], default="Not Mentioned")
    stipend = extract_field(text, ["Stipend", "Salary"], default="Unpaid")
    application_deadline = extract_field(text, ["Application Deadline", "Apply By"], default="2025-03-01")
    required_skills = extract_list(text, ["Skills", "Required Skills"])
    job_description = extract_field(text, ["Description", "Job Role"], default="Not Available")
    company_website = extract_field(text, ["Website", "More Information"], default="Not Provided")
    internship_type = extract_field(text, ["Internship Type"], default="Part-time")

    # Construct structured internship data
    return {
        "title": title,
        "company_name": company_name,
        "location": location,
        "duration": duration,
        "stipend": stipend,
        "application_deadline": application_deadline,
        "required_skills": required_skills,
        "job_description": job_description,
        "company_website": company_website,
        "internship_type": internship_type
    }

# Helper function to extract single field from text
def extract_field(text, keywords, default=""):
    for keyword in keywords:
        match = re.search(rf"{keyword}[:\-]?\s*(.*)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return default

# Helper function to extract list values
def extract_list(text, keywords):
    for keyword in keywords:
        match = re.search(rf"{keyword}[:\-]?\s*(.*)", text, re.IGNORECASE)
        if match:
            return [skill.strip() for skill in match.group(1).split(",")]
    return []

import json
import re
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from PIL import Image, ImageFilter
import pytesseract
import google.generativeai as genai

genai.configure(api_key="AIzaSyCLDQgKnO55UQrnFsL2d79fxanIn_AL0WA")

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def preprocess_image(image):
    """Enhances image quality for better OCR recognition."""
    image = image.convert("L")  # Convert to grayscale
    image = image.filter(ImageFilter.SHARPEN)  # Sharpen image
    return image

def extract_text_from_image(image):
    """Extracts raw text from the uploaded internship image using OCR."""
    processed_image = preprocess_image(image)
    extracted_text = pytesseract.image_to_string(processed_image, lang="eng")
    return extracted_text.strip()

def analyze_text_with_gemini_api(ocr_text):
    """Sends extracted text to Gemini API and retrieves structured internship data."""
    prompt = f"""
    Extract internship posting details from the following text and return in JSON format.
    **Extracted Text:**
    {ocr_text}
    **Output Format (Ensure All Fields Exist & Fill Missing Ones)**:
    {{
        "title": "Extracted Internship Title or 'No Data Available'",
        "company_name": "Extracted Company Name or 'No Data Available'",
        "location": "Extracted Location or 'No Data Available'",
        "duration": "Extracted Duration or 'No Data Available'",
        "stipend": "Extracted Stipend or 'No Data Available'",
        "application_deadline": "YYYY-MM-DD or 'No Data Available'",
        "required_skills": [
            "Skill 1",
            "Skill 2",
            "Infer if missing"
        ],
        "education_requirements": "Extracted Qualification or 'No Data Available'",
        "job_description": "Extracted Internship Description or 'No Data Available'",
        "company_website": "Extracted Website or 'No Data Available'",
        "job_link": "Extracted Internship Link or 'No Data Available'",
        "internship_type": "Full-time/Part-time (Infer if missing)"
    }}
    **Ensure output is valid JSON with no additional text.**
    """
    # Call Gemini AI Model
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt)

    try:
        # ✅ Clean AI response (remove Markdown formatting)
        cleaned_response = re.sub(r"```json|```", "", response.text).strip()
        json_output = json.loads(cleaned_response)  # Convert to JSON

        # ✅ Ensure all required fields have values (fallback to "No Data Available")
        required_fields = {
            "title": "No Data Available",
            "company_name": "No Data Available",
            "location": "No Data Available",
            "duration": "No Data Available",
            "stipend": "No Data Available",
            "application_deadline": "No Data Available",
            "required_skills": [],
            "education_requirements": "No Data Available",
            "job_description": "No Data Available",
            "company_website": "No Data Available",
            "job_link": "No Data Available",
            "internship_type": "No Data Available"
        }
        for key, default_value in required_fields.items():
            if key not in json_output or not json_output[key]:
                json_output[key] = default_value

        return json_output
    except json.JSONDecodeError as e:
        print("\n❌ AI Response Error:", str(e))
        return {"error": "AI processing failed. Please try again."}

@csrf_exempt
def upload_internship_image(request):
    """Handles internship image uploads, extracts text using OCR, and refines it using AI."""
    if request.method == "POST":
        try:
            internship_image = request.FILES.get("image")
            if not internship_image:
                return JsonResponse({"error": "No image provided"}, status=400)

            # Step 1: Extract raw text
            raw_text = extract_text_from_image(Image.open(internship_image))

            # Step 2: Process AI enhancement
            internship_data = analyze_text_with_gemini_api(raw_text)
            if "error" in internship_data:
                return JsonResponse({"error": "AI processing failed. Please try again."}, status=500)


            return JsonResponse({"message": "Text extracted successfully", "data": internship_data}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def post_internship(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            role = data.get('role')
            userid = data.get('userId')
            auto_approval_setting = superadmin_collection.find_one({"key": "auto_approval"})
            is_auto_approval = auto_approval_setting.get("value", False) if auto_approval_setting else False

            is_publish = None

            if role == 'admin':
                if is_auto_approval:
                    is_publish = True
            elif role == 'superadmin':
                is_publish = True

            application_deadline_str = data.get('application_deadline')

            # Convert application_deadline to a timezone-aware datetime
            try:
                application_deadline = datetime.strptime(application_deadline_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return JsonResponse({"error": "Invalid date format for application_deadline. Use YYYY-MM-DD."}, status=400)

            now = datetime.now(timezone.utc)
            current_status = "Active" if application_deadline >= now else "Expired"

            # Ensure required fields are present
            required_fields = [
                'title', 'company_name', 'location', 'duration', 'stipend',
                'application_deadline', 'skills_required', 'job_description',
                'company_website', 'internship_type'
            ]
            for field in required_fields:
                if field not in data:
                    return JsonResponse({"error": f"Missing required field: {field}"}, status=400)

            # Prepare internship data for insertion
            internship_post = {
                "internship_data": {
                    "title": data['title'],
                    "company_name": data['company_name'],
                    "location": data['location'],
                    "industry_type": data.get('industry_type', "NA"),
                    "duration": data['duration'],
                    "stipend": data['stipend'],
                    "application_deadline": application_deadline,
                    "required_skills": data['skills_required'],
                    "technical_skills": data.get('technical_skills', []),
                    "soft_skills": data.get('soft_skills', []),
                    "additional_skills": data.get('additional_skills', []),
                    "education_requirements": data.get('education_requirements', "NA"),
                    "job_description": data['job_description'],
                    "company_website": data['company_website'],
                    "internship_type": data['internship_type'],
                    "documents_required": data.get('documents_required', "NA"),
                    "internship_posting_date": data.get('internship_posting_date', "NA"),
                    "interview_start_date": data.get('interview_start_date', "NA"),
                    "interview_end_date": data.get('interview_end_date', "NA"),
                    "internship_link": data.get('internship_link', "NA"),
                    "selection_process": data.get('selection_process', "NA"),
                    "steps_to_apply": data.get('steps_to_apply', "NA")
                },
                "admin_id" if role == "admin" else "superadmin_id": userid,
                "is_publish": is_publish,
                "status": current_status,
                "updated_at": datetime.now(timezone.utc)
            }
            print(internship_post)

            # Insert into MongoDB
            internship_collection.insert_one(internship_post)

            # Return success response
            return JsonResponse({"message": "Internship posted successfully, awaiting approval."}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method. Only POST is allowed."}, status=405)

@csrf_exempt
def manage_internships(request):
    if request.method == 'GET':
        # Retrieve JWT token from Authorization Header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({'error': 'No token provided'}, status=401)

        jwt_token = auth_header.split(" ")[1]

        try:
            # Decode JWT token
            decoded_token = jwt.decode(jwt_token, 'secret', algorithms=["HS256"])
            role = decoded_token.get('role')
            admin_user = decoded_token.get('admin_user') if role == "admin" else decoded_token.get('superadmin_user')

            if not admin_user:
                return JsonResponse({"error": "Invalid token"}, status=401)

            # Fetch internships from MongoDB based on admin_user
            internships = internship_collection.find({"admin_id": admin_user} if role == "admin" else {})
            internship_list = []
            for internship in internships:
                internship["_id"] = str(internship["_id"])  # Convert ObjectId to string
                internship_list.append(internship)

            return JsonResponse({"internships": internship_list}, status=200)

        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'JWT token has expired'}, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({'error': f'Invalid JWT token: {str(e)}'}, status=401)
        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def get_published_internships(request):
    try:
        internship_list = []
        published_internships = internship_collection.find({"is_publish": True})
        for internship in published_internships:
            internship["_id"] = str(internship["_id"])
            # Calculate total views
            total_views = sum(view["count"] for view in internship.get("views", []))
            # Remove views field and add total_views
            internship.pop("views", None)
            internship["total_views"] = total_views
            internship_list.append(internship)
        return JsonResponse({"internships": internship_list}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def review_internship(request, internship_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            action = data.get("action")
            if action not in ["approve", "reject"]:
                return JsonResponse({"error": "Invalid action"}, status=400)

            internship = internship_collection.find_one({"_id": ObjectId(internship_id)})
            if not internship:
                return JsonResponse({"error": "Internship not found"}, status=404)

            is_publish = True if action == "approve" else False
            internship_collection.update_one(
                {"_id": ObjectId(internship_id)},
                {"$set": {"is_publish": is_publish, "updated_at": datetime.now()}}
            )

            message = "Internship approved and published successfully" if is_publish else "Internship rejected successfully"
            return JsonResponse({"message": message}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"error": "Invalid request method"}, status=400)

@csrf_exempt
def get_internships(request):
    try:
        internships = internship_collection.find()
        internship_list = []
        
        for internship in internships:
            # Convert ObjectId to string
            internship["_id"] = str(internship["_id"])

            # Convert application_deadline to date format if it's a string
            if "application_deadline" in internship and internship["application_deadline"]:
                deadline = internship["application_deadline"]
                
                try:
                    # Try parsing as full datetime format
                    formatted_deadline = datetime.strptime(deadline, "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%d")
                except ValueError:
                    try:
                        # Try parsing as plain date format
                        formatted_deadline = datetime.strptime(deadline, "%Y-%m-%d").strftime("%Y-%m-%d")
                    except ValueError:
                        # If parsing fails, keep original value
                        formatted_deadline = deadline
                
                internship["application_deadline"] = formatted_deadline  # Update with formatted date

            # Fetch admin details using admin_id
            admin_id = internship.get("admin_id")
            admin_name = "Unknown Admin"


            if admin_id:
                try:
                    admin = admin_collection.find_one({"_id": ObjectId(admin_id)})  # Convert to ObjectId
                    if admin:
                        admin_name = admin.get("name", "Unknown Admin")
                except Exception as e:
                    print("Error fetching admin:", e)

            # Add admin name to the response
            internship["admin_name"] = admin_name

            internship_list.append(internship)

        return JsonResponse({"internships": internship_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
def get_internship_id(request, internship_id):
    """
    Get an internship by its ID.
    """
    if request.method == 'GET':
        try:
            internship = internship_collection.find_one({"_id": ObjectId(internship_id)})
            if not internship:
                return JsonResponse({"error": "Internship not found"}, status=404)

            internship["_id"] = str(internship["_id"])  # Convert ObjectId to string

            # Convert application_deadline to only date format (YYYY-MM-DD)
            if "application_deadline" in internship and internship["application_deadline"]:
                if isinstance(internship["application_deadline"], datetime):  # If it's a datetime object
                    internship["application_deadline"] = internship["application_deadline"].strftime("%Y-%m-%d")
                else:  # If it's a string, ensure it's correctly formatted
                    try:
                        internship["application_deadline"] = datetime.strptime(internship["application_deadline"], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
                    except ValueError:
                        pass  # Ignore if the format is unexpected

            return JsonResponse({"internship": internship}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

    
@csrf_exempt
def delete_internship(request, internship_id):
    """
    Delete an internship by its ID.
    """
    if request.method == 'DELETE':
        try:
            internship = internship_collection.find_one({"_id": ObjectId(internship_id)})
            if not internship:
                return JsonResponse({"error": "Internship not found"}, status=404)

            internship_collection.delete_one({"_id": ObjectId(internship_id)})
            return JsonResponse({"message": "Internship deleted successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def update_internship(request, internship_id):
    """
    Update an internship by its ID.
    """
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            internship = internship_collection.find_one({"_id": ObjectId(internship_id)})
            if not internship:
                return JsonResponse({"error": "Internship not found"}, status=404)

            # Exclude the _id field from the update
            if '_id' in data:
                del data['_id']

            # Separate the 'edited' field from the rest of the data
            edited_value = data.pop("edited", None)

            # Prepare the update data for nested fields
            update_data = {"$set": {f"internship_data.{key}": value for key, value in data.items()}}

            # If 'edited' is provided, add it to the root level update
            if edited_value is not None:
                update_data["$set"]["edited"] = edited_value

            internship_collection.update_one({"_id": ObjectId(internship_id)}, update_data)
            updated_internship = internship_collection.find_one({"_id": ObjectId(internship_id)})
            updated_internship["_id"] = str(updated_internship["_id"])  # Convert ObjectId to string
            return JsonResponse({"internship": updated_internship}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def manage_jobs(request):
    if request.method == 'GET':
        # Retrieve JWT token from Authorization Header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({'error': 'No token provided'}, status=401)
        
        jwt_token = auth_header.split(" ")[1]
        
        try:
            # Decode JWT token
            decoded_token = jwt.decode(jwt_token, JWT_SECRET, algorithms=["HS256"])
            role = decoded_token.get('role')
            admin_user = decoded_token.get('admin_user') if role == "admin" else decoded_token.get('superadmin_user')
            
            if not admin_user:
                return JsonResponse({"error": "Invalid token"}, status=401)
            
            # Fetch jobs from MongoDB based on admin_user
            jobs = job_collection.find({"admin_id": admin_user} if role == "admin" else {})
            job_list = [{**job, "_id": str(job["_id"])} for job in jobs]
            
            return JsonResponse({"jobs": job_list}, status=200)
        
        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'JWT token has expired'}, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({'error': f'Invalid JWT token: {str(e)}'}, status=401)
        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def get_jobs(request):
    if request.method == 'GET':
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({'error': 'JWT token missing or invalid'}, status=401)

        jwt_token = auth_header.split(" ")[1]

        try:
            decoded_token = jwt.decode(jwt_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            admin_user = decoded_token.get('admin_user')

            jobs_list = []
            achievements_list = []

            # Counters for job & internship approvals, rejections, pending, and total achievements
            total_jobs = 0
            total_internships = 0
            total_achievements = 0
            approvals = 0
            rejections = 0
            pending = 0

            # Fetch jobs
            jobs = job_collection.find({'admin_id': admin_user})
            for job in jobs:
                job['_id'] = str(job['_id'])
                job['type'] = 'job'

                # Rename 'job_location' to 'location' if it exists
                if "job_data" in job and "job_location" in job["job_data"]:
                    job["job_data"]["location"] = job["job_data"].pop("job_location")

                # Calculate total views for jobs
                total_views = sum(view["count"] for view in job.get("views", []))
                job.pop("views", None)
                job["total_views"] = total_views

                # Update approval status count
                if job.get("is_publish") is True:
                    approvals += 1
                elif job.get("is_publish") is False:
                    rejections += 1
                else:
                    pending += 1

                total_jobs += 1
                jobs_list.append(job)

            # Fetch internships
            internships = internship_collection.find({'admin_id': admin_user})
            for internship in internships:
                internship['_id'] = str(internship['_id'])
                internship['type'] = 'internship'

                # Calculate total views for internships
                total_views = sum(view["count"] for view in internship.get("views", []))
                internship.pop("views", None)
                internship["total_views"] = total_views

                # Update approval status count
                if internship.get("is_publish") is True:
                    approvals += 1
                elif internship.get("is_publish") is False:
                    rejections += 1
                else:
                    pending += 1

                total_internships += 1
                jobs_list.append(internship)

            # Fetch achievements
            achievements = achievement_collection.find({'admin_id': admin_user})
            for achievement in achievements:
                achievement['_id'] = str(achievement['_id'])
                achievement['type'] = 'achievement'
                achievements_list.append(achievement)
                total_achievements += 1  # Count total achievements

            return JsonResponse({
                'jobs': jobs_list,
                'achievements': achievements_list,
                'approvals': approvals,
                'rejections': rejections,
                'pending': pending,
                'total_jobs': total_jobs,
                'total_internships': total_internships,
                'total_achievements': total_achievements  # Added total achievements count
            }, status=200)

        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'JWT token has expired'}, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({'error': f'Invalid JWT token: {str(e)}'}, status=401)
        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)

    return JsonResponse({'error': 'Invalid request method'}, status=405)

#===================================================================Admin-Mails====================================================================== 

@csrf_exempt
def get_admin_inbox(request):
    if request.method == "GET":
        # Retrieve JWT token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'JWT token missing'}, status=401)

        jwt_token = auth_header.split(' ')[1]

        try:
            # Decode the JWT token
            decoded_token = jwt.decode(jwt_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            admin_id = decoded_token.get('admin_user')

            # Check if admin_id is present in the token
            if not admin_id:
                return JsonResponse({"error": "Invalid token: No admin_id"}, status=401)

            # Fetch jobs, internships, achievements, and study materials from MongoDB where admin_id matches
            jobs = list(job_collection.find({"admin_id": admin_id}))
            internships = list(internship_collection.find({"admin_id": admin_id}))
            achievements = list(achievement_collection.find({"admin_id": admin_id}))
            study_materials = list(study_material_collection.find({"admin_id": admin_id}))

            # Convert MongoDB ObjectId to string for JSON serialization
            def convert_objectid_to_str(items):
                for item in items:
                    item["_id"] = str(item["_id"])  # Convert ObjectId to string
                return items

            return JsonResponse({
                "jobs": convert_objectid_to_str(jobs),
                "internships": convert_objectid_to_str(internships),
                "achievements": convert_objectid_to_str(achievements),
                "study_materials": convert_objectid_to_str(study_materials),
            }, safe=False, status=200)

        except jwt.ExpiredSignatureError:
            return JsonResponse({"error": "Token has expired"}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({"error": "Invalid token"}, status=401)
        except Exception as e:
            return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def submit_feedback(request):
    if request.method == "POST":
        try:
            # Decode the JWT token
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return JsonResponse({'error': 'Invalid token'}, status=401)

            token = auth_header.split(' ')[1]
            decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

            # Parse the request body
            data = json.loads(request.body)
            item_id = data.get('item_id')
            item_type = data.get('item_type')
            feedback = data.get('feedback')

            if not item_id or not item_type or not feedback:
                return JsonResponse({'error': 'Missing required fields'}, status=400)

            # Determine the collection based on item_type
            if item_type == "job":
                collection = job_collection
            elif item_type == "internship":
                collection = internship_collection
            elif item_type == "achievement":
                collection = achievement_collection
            else:
                return JsonResponse({'error': 'Invalid item type'}, status=400)

            # Fetch the item data
            item_data = collection.find_one({'_id': ObjectId(item_id)})
            if not item_data:
                return JsonResponse({'error': f'Invalid item_id: {item_type.capitalize()} not found'}, status=404)

            admin_id = item_data.get('admin_id')
            item_name = item_data.get('job_data', {}).get('title') or item_data.get('internship_data', {}).get('title') or item_data.get('name')

            if not admin_id:
                return JsonResponse({'error': 'admin_id not found for the provided item'}, status=404)

            # Store the feedback in the Reviews collection
            review_document = {
                'admin_id': admin_id,
                'item_id': item_id,
                'item_name': item_name,
                'item_type': item_type,
                'feedback': feedback,
                'timestamp': datetime.now().isoformat()
            }
            reviews_collection.insert_one(review_document)

            # Update the is_publish field in the respective collection to False
            collection.update_one(
                {'_id': ObjectId(item_id)},
                {'$set': {'is_publish': False}}
            )

            return JsonResponse({'message': 'Feedback submitted successfully and item unpublished'}, status=200)

        except jwt.ExpiredSignatureError:
            return JsonResponse({"error": "Token has expired"}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({"error": "Invalid token"}, status=401)
        except Exception as e:
            return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


# ============================================================== STUDY MATERIALS ======================================================================================
#post study_material

@csrf_exempt
def post_study_material(request):
    if request.method == 'POST':
        try:
            # Get JWT token from Authorization Header
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith("Bearer "):
                return JsonResponse({"error": "No token provided"}, status=401)
            jwt_token = auth_header.split(" ")[1]
            # Decode JWT token
            try:
                decoded_token = jwt.decode(jwt_token, 'secret', algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return JsonResponse({"error": "Token expired"}, status=401)
            except jwt.InvalidTokenError:
                return JsonResponse({"error": "Invalid token"}, status=401)
            role = decoded_token.get('role')
            auto_approval_setting = superadmin_collection.find_one({"key": "auto_approval"})
            is_auto_approval = auto_approval_setting.get("value", False) if auto_approval_setting else False
            if role == 'admin':
                admin_id = decoded_token.get('admin_user')
                if not admin_id:
                    return JsonResponse({"error": "Invalid token"}, status=401)
                is_publish = True
            elif role == 'superadmin':
                superadmin_id = decoded_token.get('superadmin_user')
                if not superadmin_id:
                    return JsonResponse({"error": "Invalid token"}, status=401)
                is_publish = True
            # Parse incoming JSON data
            data = json.loads(request.body)
            # Ensure required fields are present
            required_fields = ['type', 'title', 'description', 'category', 'links']
            for field in required_fields:
                if field not in data:
                    return JsonResponse({"error": f"Missing required field: {field}"}, status=400)
            # Prepare study material document
            study_material_post = {
                "type": data['type'],
                "title": data['title'],
                "description": data['description'],
                "category": data['category'],
                "links": data['links'],  # Links now include the topic field

                "links": data['links'],  # Links now include the topic field
                "admin_id" if role == "admin" else "superadmin_id": admin_id if role == "admin" else superadmin_id,
                "is_publish": is_publish,
                "updated_at": datetime.utcnow()
            }
            # Insert into MongoDB
            study_material_collection.insert_one(study_material_post)
            return JsonResponse({"message": "Study Material posted successfully"}, status=200)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON format."}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method. Only POST is allowed."}, status=405)


@csrf_exempt
def get_categories(request):
    if request.method == 'GET':
        try:
            import re
            # Get query parameters
            material_type = request.GET.get('type')
            query = request.GET.get('query', '')
            if not material_type:
                return JsonResponse({"error": "Type parameter is required"}, status=400)
            # Create regex pattern for case-insensitive search
            regex_pattern = re.compile(f".*{re.escape(query)}.*", re.IGNORECASE)
            # Fetch distinct categories where:
            # - 'type' matches the provided type
            # - 'category' field exists
            # - 'category' matches the query (if any)
            categories = list(study_material_collection.distinct(
                "category",
                {
                    "type": material_type,
                    "category": {"$exists": True, "$regex": regex_pattern}
                }
            ))
            # Debugging logs
            if not categories:
                print(f"No categories found for type '{material_type}'. Logging collection content:")
                for doc in study_material_collection.find({"type": material_type, "category": {"$exists": True}}):
                    print(doc)
            return JsonResponse({"categories": categories}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method. Only GET is allowed."}, status=405)


# @csrf_exempt
# @api_view(['POST'])
# def post_study_material(request):
#     if request.method == 'POST':
#         try:
#             # Get JWT token from Authorization Header
#             auth_header = request.headers.get('Authorization')
#             if not auth_header or not auth_header.startswith("Bearer "):
#                 return JsonResponse({"error": "No token provided"}, status=401)

#             jwt_token = auth_header.split(" ")[1]

#             # Decode JWT token
#             try:
#                 decoded_token = jwt.decode(jwt_token, 'secret', algorithms=["HS256"])
#             except jwt.ExpiredSignatureError:
#                 return JsonResponse({"error": "Token expired"}, status=401)
#             except jwt.InvalidTokenError:
#                 return JsonResponse({"error": "Invalid token"}, status=401)

#             role = decoded_token.get('role')
#             auto_approval_setting = superadmin_collection.find_one({"key": "auto_approval"})
#             is_auto_approval = auto_approval_setting.get("value", False) if auto_approval_setting else False

#             if role == 'admin':
#                 admin_id = decoded_token.get('admin_user')
#                 if not admin_id:
#                     return JsonResponse({"error": "Invalid token"}, status=401)
#                 is_publish = True

#             elif role == 'superadmin':
#                 superadmin_id = decoded_token.get('superadmin_user')
#                 if not superadmin_id:
#                     return JsonResponse({"error": "Invalid token"}, status=401)
#                 is_publish = True

#             # Parse incoming JSON data
#             data = json.loads(request.body)

#             # Ensure required fields are present
#             required_fields = ['exam', 'title', 'description', 'source_links']
#             for field in required_fields:
#                 if field not in data:
#                     return JsonResponse({"error": f"Missing required field: {field}"}, status=400)

#             study_material_post = {
#                 "type": "exam",
#                 "exam": data['exam'],
#                 "title": data['title'],
#                 "description": data['description'],
#                 "source_links": data['source_links'].split(','),  # Assuming links are comma-separated
#                 "admin_id" if role == "admin" else "superadmin_id": admin_id if role == "admin" else superadmin_id,
#                 "is_publish": is_publish,
#                 "updated_at": datetime.utcnow()
#             }

#             # Insert into MongoDB
#             study_material_collection.insert_one(study_material_post)

#             return JsonResponse({"message": "Exam Material posted successfully"}, status=200)

#         except json.JSONDecodeError:
#             return JsonResponse({"error": "Invalid JSON format."}, status=400)
#         except Exception as e:
#             return JsonResponse({"error": str(e)}, status=500)

#     return JsonResponse({"error": "Invalid request method. Only POST is allowed."}, status=405)

# @csrf_exempt
# def exam_topic(request):
#     if request.method == 'GET'
@csrf_exempt
def get_categories(request):
    if request.method == 'GET':
        try:
            import re
            # Get query parameters
            material_type = request.GET.get('type')
            query = request.GET.get('query', '')
            if not material_type:
                return JsonResponse({"error": "Type parameter is required"}, status=400)
            # Create regex pattern for case-insensitive search
            regex_pattern = re.compile(f".*{re.escape(query)}.*", re.IGNORECASE)
            # Fetch distinct categories where:
            # - 'type' matches the provided type
            # - 'category' field exists
            # - 'category' matches the query (if any)
            categories = list(study_material_collection.distinct(
                "category",
                {
                    "type": material_type,
                    "category": {"$exists": True, "$regex": regex_pattern}
                }
            ))
            # Debugging logs
            if not categories:
                print(f"No categories found for type '{material_type}'. Logging collection content:")
                for doc in study_material_collection.find({"type": material_type, "category": {"$exists": True}}):
                    print(doc)
            return JsonResponse({"categories": categories}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method. Only GET is allowed."}, status=405)

@csrf_exempt
def get_topics_by_category(request):
    if request.method == 'GET':
        try:
            category = request.GET.get('category')
            if not category:
                return JsonResponse({"error": "Category is required"}, status=400)

            # Use aggregation to unwind the links array and extract distinct topics
            pipeline = [
                {"$match": {"category": category}},
                {"$unwind": "$links"},
                {"$group": {"_id": "$links.topic"}},
                {"$project": {"_id": 0, "topic": "$_id"}}
            ]
            topics = list(study_material_collection.aggregate(pipeline))
            topics = [topic['topic'] for topic in topics]

            return JsonResponse({"topics": topics}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method. Only GET is allowed."}, status=405)

@csrf_exempt
def get_materials_by_topic(request):
    if request.method == 'GET':
        try:
            topic = request.GET.get('topic')
            if not topic:
                return JsonResponse({"error": "Topic is required"}, status=400)

            # Use aggregation to unwind the links array and filter by topic
            pipeline = [
                {"$unwind": "$links"},
                {"$match": {"links.topic": topic}},
                {"$group": {
                    "_id": "$_id",
                    "type": {"$first": "$type"},
                    "title": {"$first": "$title"},
                    "description": {"$first": "$description"},
                    "category": {"$first": "$category"},
                    "links": {"$push": "$links"},
                    "superadmin_id": {"$first": "$superadmin_id"},
                    "is_publish": {"$first": "$is_publish"},
                    "updated_at": {"$first": "$updated_at"}
                }}
            ]
            materials = list(study_material_collection.aggregate(pipeline))

            # Convert ObjectId to string
            for material in materials:
                material['_id'] = str(material['_id'])

            return JsonResponse({"materials": materials}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method. Only GET is allowed."}, status=405)

@csrf_exempt
def manage_study_materials(request):
    if request.method == 'GET':
        # Retrieve JWT token from Authorization Header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({'error': 'No token provided'}, status=401)

        jwt_token = auth_header.split(" ")[1]

        try:
            # Decode JWT token
            decoded_token = jwt.decode(jwt_token, 'secret', algorithms=["HS256"])
            role = decoded_token.get('role')
            admin_user = decoded_token.get('admin_user') if role == "admin" else decoded_token.get('superadmin_user')

            if not admin_user:
                return JsonResponse({"error": "Invalid token"}, status=401)

            # Fetch study materials from MongoDB based on admin_user
            study_materials = study_material_collection.find({"admin_id": admin_user} if role == "admin" else {})
            study_material_list = []
            for study in study_materials:
                study["_id"] = str(study["_id"])  # Convert ObjectId to string
                study_material_list.append(study)

            return JsonResponse({"study_materials": study_material_list}, status=200)

        except jwt.ExpiredSignatureError:
            return JsonResponse({'error': 'JWT token has expired'}, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({'error': f'Invalid JWT token: {str(e)}'}, status=401)
        except Exception as e:
            return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

@csrf_exempt
def get_study_material_by_id(request, study_material_id):
    """
    Fetch a single study material by its ID.
    """
    try:
        study_material = study_material_collection.find_one({"_id": ObjectId(study_material_id)})
        if not study_material:
            return JsonResponse({"error": "Study material not found"}, status=404)

        study_material["_id"] = str(study_material["_id"])  # Convert ObjectId to string
        return JsonResponse({"study_material": study_material}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def update_study_material(request, study_material_id):
    """
    Update a study material by its ID.
    """
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            study_material = study_material_collection.find_one({"_id": ObjectId(study_material_id)})
            if not study_material:
                return JsonResponse({"error": "Study material not found"}, status=404)

            # Exclude the _id field from the update
            if '_id' in data:
                del data['_id']

            study_material_collection.update_one({"_id": ObjectId(study_material_id)}, {"$set": data})
            updated_study_material = study_material_collection.find_one({"_id": ObjectId(study_material_id)})
            updated_study_material["_id"] = str(updated_study_material["_id"])  # Convert ObjectId to string
            return JsonResponse({"study_material": updated_study_material}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def delete_study_material(request, study_material_id):
    """
    Delete a study material by its ID.
    """
    if request.method == 'DELETE':
        try:
            study_material = study_material_collection.find_one({"_id": ObjectId(study_material_id)})
            if not study_material:
                return JsonResponse({"error": "Study material not found"}, status=404)

            study_material_collection.delete_one({"_id": ObjectId(study_material_id)})
            return JsonResponse({"message": "Study material deleted successfully"}, status=200)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid method"}, status=405)

def fetch_review(request):
    """Extracts JWT, validates it, and fetches all review documents for the admin ID."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JsonResponse({"error": "Unauthorized access"}, status=401)

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return JsonResponse({"error": "Token has expired"}, status=401)
    except jwt.InvalidTokenError:
        return JsonResponse({"error": "Invalid token"}, status=401)

    admin_id = payload.get("admin_user")
    if not admin_id:
        return JsonResponse({"error": "Invalid token payload"}, status=401)

    print(f"Querying for admin_id: {admin_id}")  # Log the query
    reviews_cursor = reviews_collection.find({"admin_id": admin_id})  # Fetch all matching documents

    reviews_list = []
    for review in reviews_cursor:
        formatted_review = {
            "review_id": str(review["_id"]),  # Convert ObjectId to string
            "admin_id": review["admin_id"],
            "item_id": review["item_id"],
            "item_name": review.get("item_name", ""),  # Use `.get()` to avoid KeyError
            "item_type": review["item_type"],
            "feedback": review["feedback"],
            "timestamp": review["timestamp"],
        }
        reviews_list.append(formatted_review)

    # Return an empty list if no reviews are found
    return JsonResponse({"reviews": reviews_list}, status=200, safe=False)

#===============================================================Super-Admin-Mails====================================================================== 

@csrf_exempt
def get_contact_messages(request):
    if request.method == "GET":
        try:
            # Fetch all messages from the contact_us collection
            messages = list(contactus_collection.find({}, {"_id": 1, "name": 1, "contact": 1, "message": 1, "timestamp": 1}))

            # Format timestamp and convert `_id` to string
            for message in messages:
                message["_id"] = str(message["_id"])  # Convert ObjectId to string
                if "timestamp" in message and message["timestamp"]:
                    message["timestamp"] = message["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    message["timestamp"] = "N/A"

            return JsonResponse({"messages": messages}, status=200)

        except Exception as e:
            # Log the error and return a 500 response
            print(f"Error: {e}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@csrf_exempt
def reply_to_message(request):
    """
    API to reply to a contact message.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            message_id = data.get("message_id")  # Message document _id
            reply_message = data.get("reply_message")  # Admin's reply text

            if not message_id or not reply_message:
                return JsonResponse({"error": "Message ID and reply message are required."}, status=400)

            # Update the existing message with the reply
            result = contactus_collection.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": {"reply_message": reply_message}}
            )

            if result.modified_count == 0:
                return JsonResponse({"error": "Message not found or already updated."}, status=404)

            return JsonResponse({"success": "Reply sent successfully!"}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=405)

@csrf_exempt
def get_jobs_with_admin(request):
    """
    Fetch all jobs and map them with admin names.
    """
    try:
        # Fetch all jobs from the jobs collection
        jobs = job_collection.find({}, {"_id": 1, "admin_id": 1, "job_data": 1, "updated_at": 1})

        job_list = []

        for job in jobs:
            job["_id"] = str(job["_id"])  # Convert ObjectId to string
            job["updated_at"] = job.get("updated_at", "N/A")

            # Fetch admin details using admin_id
            admin_id = job.get("admin_id")
            admin_name = "Unknown Admin"

            if admin_id:
                admin = admin_collection.find_one({"_id": ObjectId(admin_id)})
                if admin:
                    admin_name = admin.get("name", "Unknown Admin")

            # Append job details with mapped admin name
            job_list.append({
                "admin_name": admin_name,
                "message": f"{admin_name} posted a job",
                "job_data": job.get("job_data", {}),
                "timestamp": job["updated_at"]
            })

        return JsonResponse({"jobs": job_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    
@csrf_exempt
def get_achievements_with_admin(request):
    """
    Fetch all achievements and correctly map them with admin names.
    """
    try:
        achievements = achievement_collection.find({}, {"_id": 1, "user_id": 1, "achievement_description": 1, "achievement_type": 1, "company_name": 1, "date_of_achievement": 1, "updated_at": 1})

        achievement_list = []

        for achievement in achievements:
            achievement["_id"] = str(achievement["_id"])  # Convert ObjectId to string
            achievement["updated_at"] = achievement.get("updated_at", "N/A")

            # Fetch admin details using user_id
            admin_id = achievement.get("user_id")
            admin_name = "Super Admin"

            if admin_id:
                admin = admin_collection.find_one({"_id": ObjectId(admin_id)})
                if admin:
                    admin_name = admin.get("name", "Super Admin")

            # Append achievement details with mapped admin name
            achievement_list.append({
                "admin_name": admin_name,
                "message": f"{admin_name} posted an achievement",
                "achievement_data": {
                    "description": achievement.get("achievement_description", "No description"),
                    "type": achievement.get("achievement_type", "Unknown"),
                    "company": achievement.get("company_name", "Not specified"),
                    "date": achievement.get("date_of_achievement", "Unknown"),
                },
                "timestamp": achievement["updated_at"]
            })

        return JsonResponse({"achievements": achievement_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def get_internships_with_admin(request):
    """
    Fetch all internships and correctly map them with admin names.
    """
    try:
        internships = internship_collection.find({}, {"_id": 1, "admin_id": 1, "internship_data": 1, "updated_at": 1})

        internship_list = []

        for internship in internships:
            internship["_id"] = str(internship["_id"])  # Convert ObjectId to string
            internship["updated_at"] = internship.get("updated_at", "N/A")

            # Extract internship details from nested structure
            internship_data = internship.get("internship_data", {})

            # Fetch admin details using admin_id
            admin_id = internship.get("admin_id")
            admin_name = "Super Admin"

            if admin_id:
                admin = admin_collection.find_one({"_id": ObjectId(admin_id)})
                if admin:
                    admin_name = admin.get("name", "Super Admin")

            # Append internship details with all fields
            internship_list.append({
                "admin_name": admin_name,
                "message": f"{admin_name} posted an internship",
                "internship_data": {
                    "title": internship_data.get("title", "No title"),
                    "company": internship_data.get("company_name", "Not specified"),
                    "location": internship_data.get("location", "Unknown"),
                    "duration": internship_data.get("duration", "Unknown"),
                    "stipend": internship_data.get("stipend", "N/A"),
                    "deadline": internship_data.get("application_deadline", "N/A"),
                    "description": internship_data.get("job_description", "No description"),
                    "job_link": internship_data.get("job_link", "N/A"),
                    "education_requirements": internship_data.get("education_requirements", "N/A"),
                    "required_skills": internship_data.get("required_skills", []),
                    "internship_type": internship_data.get("internship_type", "N/A"),
                    "company_website": internship_data.get("company_website", "N/A"),
                    "status": internship_data.get("status", "N/A"),
                    "is_publish": internship_data.get("is_publish", False),
                },
                "timestamp": internship["updated_at"]
            })

        return JsonResponse({"internships": internship_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    
@csrf_exempt
def get_study_materials_with_admin(request):
    try:
        study_materials = study_material_collection.find({}, {"_id": 1, "admin_id": 1, "study_material_data": 1, "updated_at": 1})

        study_material_list = []

        for material in study_materials:
            material["_id"] = str(material["_id"])
            material["updated_at"] = material.get("updated_at", "N/A")

            study_material_data = material.get("study_material_data", {})  # Ensure this exists

            admin_id = material.get("admin_id")
            admin_name = "Super Admin"

            if admin_id:
                admin = admin_collection.find_one({"_id": ObjectId(admin_id)})
                if admin:
                    admin_name = admin.get("name", "Super Admin")

            # Ensure all fields are correctly mapped
            study_material_list.append({
                "admin_name": admin_name,
                "message": f"{admin_name} shared a study material",
                "study_material_data": {
                    "title": study_material_data.get("title", "No title"),
                    "description": study_material_data.get("description", "No description"),
                    "category": study_material_data.get("category", "Uncategorized"),
                    "text_content": study_material_data.get("text_content", "No content available"),
                    "link": study_material_data.get("link", "N/A"),
                },
                "timestamp": material["updated_at"]
            })

        return JsonResponse({"study_materials": study_material_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    
@csrf_exempt
def get_student_achievements(request):
    try:
        student_achievements = student_achievement_collection.find()
        achievement_list = []

        for achievement in student_achievements:
            student_name = achievement.get("name", "Unknown Student")
            achievement_desc = achievement.get("achievement_description", "No description")
            achievement_type = achievement.get("achievement_type", "Unknown Type")
            company = achievement.get("company_name", "Unknown Company")
            date_of_achievement = achievement.get("date_of_achievement", "Unknown Date")
            batch = achievement.get("batch", "Unknown Batch")
            photo = achievement.get("photo", None)  # Binary image data or URL

            message = f"{student_name} achieved {achievement_desc} in {achievement_type} on {date_of_achievement}"

            achievement_list.append({
                "student_name": student_name,
                "message": message,
                "achievement_data": {
                    "description": achievement_desc,
                    "type": achievement_type,
                    "company": company,
                    "date": date_of_achievement,
                    "batch": batch,
                    "photo": photo,
                    "is_approved": achievement.get("is_approved", False),
                },
                "timestamp": achievement.get("submitted_at", ""),
            })

        return JsonResponse({"student_achievements": achievement_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

      
#================================================================Profile=======================================================================================

@csrf_exempt
def get_admin_details(request, userId):
    if request.method == "GET":
        try:
            # Find the admin user by ID
            admin = admin_collection.find_one({"_id": ObjectId(userId)})

            if not admin:
                return JsonResponse(
                    {"error": "Admin with this ID does not exist"}, status=400
                )

            # Ensure profile_image field is correctly retrieved as a filename
            profile_image = admin.get("profile_image", "default.png")  # Default image if none

            # Prepare response data
            data = {
                "name": admin.get("name"),
                "email": admin.get("email"),
                "status": admin.get("status"),
                "created_at": str(admin.get("created_at")) if admin.get("created_at") else "N/A",
                "last_login": str(admin.get("last_login")) if admin.get("last_login") else "Never",
                "college_name": admin.get("college_name", "N/A"),
                "department": admin.get("department", "N/A"),
                "role": "admin",
                "profile_image": profile_image,  # Send only filename, not binary data
            }

            return JsonResponse({"message": "Admin details found", "data": data}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)
    
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from bson import ObjectId
import json

@csrf_exempt
def update_admin_profile(request, userId):
    if request.method == "PUT":
        try:
            # Parse JSON request body
            data = json.loads(request.body)

            # Find the admin user by ID
            admin = admin_collection.find_one({"_id": ObjectId(userId)})
            if not admin:
                return JsonResponse({"error": "Admin not found"}, status=404)

            # Validate request payload
            if "name" not in data:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            # Prevent email from being changed
            data.pop("email", None)

            # Update only the name
            updated_fields = {
                "name": data["name"]
            }

            admin_collection.update_one({"_id": ObjectId(userId)}, {"$set": updated_fields})

            return JsonResponse({"message": "Admin profile updated successfully"}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)


@csrf_exempt
def get_superadmin_details(request, userId):
    if request.method == "GET":
        try:
            # Find the super admin user by ID
            superadmin = superadmin_collection.find_one({"_id": ObjectId(userId)})

            if not superadmin:
                return JsonResponse(
                    {"error": "Super Admin with this ID does not exist"}, status=400
                )

            # Handle profile image (Check if image is stored as a filename or binary)
            profile_image = ""
            if "profile_image" in superadmin:
                if isinstance(superadmin["profile_image"], bytes):
                    # Convert Binary image to Base64 format
                    profile_image = "data:image/jpeg;base64," + base64.b64encode(superadmin["profile_image"]).decode('utf-8')
                elif isinstance(superadmin["profile_image"], str):
                    # If stored as a filename, return it directly
                    profile_image = superadmin["profile_image"]

            # Prepare response data
            data = {
                "name": superadmin.get("name"),
                "email": superadmin.get("email"),
                "status": superadmin.get("status", "N/A"),
                "created_at": str(superadmin.get("created_at")) if superadmin.get("created_at") else "N/A",
                "last_login": str(superadmin.get("last_login")) if superadmin.get("last_login") else "Never",
                "college_name": superadmin.get("college_name", "N/A"),
                "department": superadmin.get("department", "N/A"),
                "role": "superadmin",
                "profile_image": profile_image,  # Send either Base64 or filename
            }

            return JsonResponse(
                {"message": "Super Admin details found", "data": data}, status=200
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

@api_view(['GET', 'PUT'])
def achievement_detail(request, achievement_id):
    try:
        # Convert ID to ObjectId
        object_id = ObjectId(achievement_id)
    except:
        return Response({"error": "Invalid Achievement ID"}, status=status.HTTP_400_BAD_REQUEST)

    # Fetch achievement from MongoDB
    achievement = achievement_collection.find_one({"_id": object_id})
    if not achievement:
        return Response({"error": "Achievement not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        # Convert MongoDB document to JSON response
        achievement["_id"] = str(achievement["_id"])  # Convert ObjectId to string
        return Response(achievement, status=status.HTTP_200_OK)

    elif request.method == 'PUT':
        # Update the achievement
        updated_data = request.data
        achievement_collection.update_one(
            {"_id": object_id},
            {"$set": updated_data}
        )
        return Response({"message": "Achievement updated successfully"}, status=status.HTTP_200_OK)

@csrf_exempt
def view_count(request, id):
    if request.method == "POST":
        try:
            # Parse the request body
            data = json.loads(request.body)
            userId = data.get("userId")
            count = data.get("count", 1)
            pageType = data.get("pageType")
            applicationId = data.get("applicationId")

            print(f"Received data - userId: {userId}, count: {count}, pageType: {pageType}, applicationId: {applicationId}")

            if not userId or not pageType or not applicationId:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            # Determine the collection based on pageType
            if pageType == "job":
                collection = job_collection
            elif pageType == "internship":
                collection = internship_collection
            else:
                return JsonResponse({"error": "Invalid pageType"}, status=400)

            print(f"Using collection: {collection.name}")

            # Find the document by applicationId
            document = collection.find_one({"_id": ObjectId(applicationId)})
            if not document:
                return JsonResponse({"error": "Application not found"}, status=404)

            # Initialize or update the views array
            views = document.get("views", [])
            user_view = next((view for view in views if view["userId"] == userId), None)

            if user_view:
                # If userId exists, do not increment the count, just update the time
                user_view["count"] = 1  # Ensure the count remains 1
            else:
                views.append({"userId": userId, "count": 1})

            # Update the document with the new views array
            collection.update_one(
                {"_id": ObjectId(applicationId)},
                {"$set": {"views": views, "updated_at": datetime.now()}}
            )

            return JsonResponse({"message": "View count updated successfully"}, status=200)

        except Exception as e:
            print(f"Error: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=405)
