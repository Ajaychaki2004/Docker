import jwt
import json
import re
from datetime import datetime, timedelta, timezone
from django.http import JsonResponse
from pymongo import MongoClient
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.conf import settings
from bson import ObjectId, Binary
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
import random
import string
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64

# Create your views here.
JWT_SECRET = "secret"
JWT_ALGORITHM = "HS256"


def generate_tokens(student_user):
    access_payload = {
        "student_user": str(student_user),
        "exp": (datetime.utcnow() + timedelta(minutes=600)).timestamp(),  # Expiration in 600 minutes
        "iat": datetime.utcnow().timestamp(),  # Issued at current time
    }
    token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"jwt": token}


# MongoDB connection
client = MongoClient("mongodb+srv://ihub:ihub@cce.ksniz.mongodb.net/")
db = client["CCE"]
student_collection = db["students"]
superadmin_collection = db["superadmin"]
admin_collection = db["admin"]
job_collection = db["jobs"]
internship_collection = db['internships']
contactus_collection = db["contact_us"]
achievement_collection = db['student_achievement']
study_material_collection = db['studyMaterial']
superadmin_collection = db['superadmin']
message_collection = db['message']

# Dictionary to track failed login attempts
failed_login_attempts = {}
lockout_duration = timedelta(minutes=2)  # Time to lock out after 3 failed attempts

# function to check if password is strong
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
    subject = "Student Account Created"
    body = f"""
    Your Student account has been successfully created on the CCE platform.
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
def student_signup(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            name = data.get("name")
            email = data.get("email")
            department = data.get("department")
            year = data.get("year")
            college_name = data.get("college_name")
            password = data.get("password")

            # Check if the email already exists
            if student_collection.find_one({"email": email}):
                return JsonResponse(
                    {"error": "Student user with this email already exists"}, status=400
                )

            # Check if email is a valid college email ID
            if "@sns" not in email:
                return JsonResponse(
                    {"error": "Please enter a valid college email ID"}, status=400
                )

            # Check if the password is strong
            is_valid, error_message = is_strong_password(password)
            if not is_valid:
                return JsonResponse({"error": error_message}, status=400)

            # Hash the password
            hashed_password = make_password(password)

            # Create the student user document
            student_user = {
                "name": name,
                "department": department,
                "year": year,
                "college_name": college_name,
                "email": email,
                "password": hashed_password,
                "status": "active",  # Default status
                "last_login": None,  # No login yet
                "created_at": datetime.utcnow(),  # Account creation timestamp
            }

            # Insert the document into the collection
            student_collection.insert_one(student_user)

            # Send confirmation email with username and password
            send_confirmation_email(email, name, password)

            return JsonResponse(
                {"message": "Student user created successfully, confirmation email sent."}, status=201
            )
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

@csrf_exempt
def student_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            email = data.get("email")
            password = data.get("password")

            # Check lockout status
            if email in failed_login_attempts:
                lockout_data = failed_login_attempts[email]
                if lockout_data["count"] >= 3 and datetime.now() < lockout_data["lockout_until"]:
                    return JsonResponse(
                        {"error": "Too many failed attempts. Please try again after 2 minutes."},
                        status=403,
                    )

            # Find the student user by email
            student_user = student_collection.find_one({"email": email})
            username = student_user.get('name')
            if not student_user:
                return JsonResponse(
                    {"error": "No account found with this email"}, status=404
                )

            # Check if the account is active
            if student_user.get("status") != "active":
                return JsonResponse(
                    {"error": "This account is inactive. Please contact the admin."}, status=403
                )

            # Check the password
            if check_password(password, student_user["password"]):
                # Clear failed attempts after successful login
                failed_login_attempts.pop(email, None)

                # Update last login timestamp
                student_collection.update_one(
                    {"email": email}, {"$set": {"last_login": datetime.utcnow()}}
                )

                # Generate JWT token
                student_id = student_user.get("_id")
                tokens = generate_tokens(student_id)
                return JsonResponse({"username": student_user['name'], "token": tokens}, status=200)
            else:
                # Track failed attempts
                if email not in failed_login_attempts:
                    failed_login_attempts[email] = {"count": 1, "lockout_until": None}
                else:
                    failed_login_attempts[email]["count"] += 1
                    if failed_login_attempts[email]["count"] >= 3:
                        failed_login_attempts[email]["lockout_until"] = datetime.now() + lockout_duration

                return JsonResponse({"error": "Invalid email or password."}, status=401)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

def generate_reset_token(length=6):
    return ''.join(random.choices(string.digits, k=length))



@api_view(["POST"])
@permission_classes([AllowAny])
def student_forgot_password(request):
    try:
        email = request.data.get('email')
        user = student_collection.find_one({"email": email})
        if not user:
            return Response({"error": "Email not found"}, status=400)

        reset_token = generate_reset_token()
        expiration_time = datetime.utcnow() + timedelta(hours=1)

        student_collection.update_one(
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

@csrf_exempt   
def student_verify_otp(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            email = data.get("email")
            otp = data.get("token")

            # Find the student user by email
            student_user = student_collection.find_one({"email": email})
            if not student_user:
                return JsonResponse(
                    {"error": "No account found with this email"}, status=404
                )
            
            print(student_user.get("password_reset_token"),otp)

            # Validate the OTP
            if student_user.get("password_reset_token") == otp:
                return JsonResponse({"message": "OTP verification successful"}, status=200)
            else:
                return JsonResponse({"error": "Invalid OTP"}, status=403)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

@csrf_exempt
def student_reset_password(request):
    """Reset Password Function for Students"""
    if request.method == 'POST':
        try:
            # Parse the request payload
            data = json.loads(request.body)
            email = data.get('email')
            new_password = data.get('newPassword')

            # Validate the request data
            if not email or not new_password:
                return JsonResponse({"error": "Email and new password are required."}, status=400)

            # Fetch the student by email
            student = student_collection.find_one({"email": email})
            if not student:
                return JsonResponse({"error": "Student not found."}, status=404)

            # Hash the new password
            hashed_password = make_password(new_password)

            # Ensure hashed password starts with "pbkdf2_sha256$"
            if not hashed_password.startswith("pbkdf2_sha256$"):
                return JsonResponse({"error": "Failed to hash the password correctly."}, status=500)

            # Update the password in MongoDB
            result = student_collection.update_one(
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
def get_students(request):
    """
    API to retrieve all students.
    """
    if request.method == 'GET':
        try:
            students = student_collection.find()
            student_list = []
            for student in students:
                student['_id'] = str(student['_id'])  # Convert ObjectId to string
                del student['password']  # Don't expose passwords
                student_list.append(student)

            return JsonResponse({'students': student_list}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)

@csrf_exempt
def update_student(request, student_id):
    """
    API to update a student's profile, including status updates.
    """
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            student = student_collection.find_one({'_id': ObjectId(student_id)})
            if not student:
                return JsonResponse({'error': 'Student not found'}, status=404)

            # ✅ Add "status" to allowed fields
            allowed_fields = ['name', 'department', 'year', 'college_name', 'status']

            # Filter data to include only allowed fields
            update_data = {field: data[field] for field in allowed_fields if field in data}

            if update_data:
                # Update student in MongoDB
                student_collection.update_one({'_id': ObjectId(student_id)}, {'$set': update_data})
                return JsonResponse({'message': 'Student details updated successfully'}, status=200)
            else:
                return JsonResponse({'error': 'No valid fields provided for update'}, status=400)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


@csrf_exempt
def delete_student(request, student_id):
    """
    API to delete a student.
    """
    if request.method == 'DELETE':
        try:
            student = student_collection.find_one({'_id': ObjectId(student_id)})
            if not student:
                return JsonResponse({'error': 'Student not found'}, status=404)

            # Delete student from MongoDB
            student_collection.delete_one({'_id': ObjectId(student_id)})

            return JsonResponse({'message': 'Student deleted successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)
    
#===============================================================Profile=======================================================================

@csrf_exempt
def get_profile(request, userId):
    if request.method == "GET":
        try:
            # Find the student user by ID
            user = student_collection.find_one({"_id": ObjectId(userId)})
            
            if not user:
                return JsonResponse({"error": "User with this ID does not exist"}, status=400)

            # Ensure profile_image field is correctly retrieved as a filename
            profile_image = user.get("profile_image", "default.png")  # Default image if none

            # Prepare response data
            data = {
                "name": user.get("name"),
                "email": user.get("email"),
                "department": user.get("department", "N/A"),
                "year": user.get("year", "N/A"),
                "college_name": user.get("college_name", "N/A"),
                "status": user.get("status", "N/A"),
                "last_login": str(user.get("last_login")) if user.get("last_login") else "Never",
                "created_at": str(user.get("created_at")) if user.get("created_at") else "N/A",
                "saved_jobs": user.get("saved_jobs", []),
                "role": "student",
                "profile_image": profile_image,  # Send only filename, not binary data
            }

            return JsonResponse({"message": "Student user found", "data": data}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

@csrf_exempt
def update_profile(request, userId):
    if request.method == "PUT":
        try:
            # Parse JSON request body
            data = json.loads(request.body)

            # Find the student user by ID
            user = student_collection.find_one({"_id": ObjectId(userId)})
            if not user:
                return JsonResponse({"error": "User not found"}, status=404)

            # Prevent email from being changed
            data.pop("email", None)

            # Update only the name
            updated_fields = {key: value for key, value in data.items() if key == "name"}
            if updated_fields:
                student_collection.update_one(
                    {"_id": ObjectId(userId)}, {"$set": updated_fields}
                )

            return JsonResponse({"message": "Profile updated successfully"}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)
    
@csrf_exempt
def update_superadmin_profile(request, userId):
    if request.method == "PUT":
        try:
            # Parse JSON request body
            data = json.loads(request.body)

            # Find the super admin user by ID
            super_admin = superadmin_collection.find_one({"_id": ObjectId(userId)})
            if not super_admin:
                return JsonResponse({"error": "SuperAdmin not found"}, status=404)

            # Validate request payload
            if "name" not in data:
                return JsonResponse({"error": "Missing required fields"}, status=400)

            # Prevent email from being changed
            data.pop("email", None)

            # Update only the name
            updated_fields = {
                "name": data["name"]
            }

            superadmin_collection.update_one({"_id": ObjectId(userId)}, {"$set": updated_fields})

            return JsonResponse({"message": "SuperAdmin profile updated successfully"}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    else:
        return JsonResponse({"error": "Invalid request method"}, status=400)

       
#================================================================Jobs================================================================================================
@csrf_exempt
def save_job(request, pk):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_id = data.get("userId")
            if not user_id:
                return JsonResponse(
                    {"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST
                )

            student_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$addToSet": {"saved_jobs": pk}},
            )

            return JsonResponse({"message": "Job saved successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
def unsave_job(request, pk):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_id = data.get("userId")

            if not user_id:
                return JsonResponse(
                    {"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST
                )

            student_collection.update_one(
                {"_id": ObjectId(user_id)}, {"$pull": {"saved_jobs": pk}}
            )

            return JsonResponse({"message": "Job removed from saved"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
@csrf_exempt
def get_saved_jobs(request, user_id):
    try:
        
        if not user_id or not ObjectId.is_valid(user_id):
            return JsonResponse(
                {"error": "Invalid or missing user_id"}, status=status.HTTP_400_BAD_REQUEST
            )

        user = student_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return JsonResponse(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        saved_jobs = user.get("saved_jobs", [])

        jobs = []
        for job_id in saved_jobs:
            if not ObjectId.is_valid(job_id):
                continue  # Skip invalid ObjectIds

            job = job_collection.find_one({"_id": ObjectId(job_id)})
            if job:
                job["_id"] = str(job["_id"])
                jobs.append(job)
        
        return JsonResponse({"message": "Saved jobs retrieved successfully", "jobs": jobs})
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    
#============================================================================ Internships =============================================================================================
@csrf_exempt
def save_internship(request, pk):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_id = data.get("userId")
            if not user_id:
                return JsonResponse(
                    {"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST
                )

            student_collection.update_one(
                {"_id": ObjectId(user_id)},
                {"$addToSet": {"saved_internships": pk}},
            )

            return JsonResponse({"message": "Internship saved successfully"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
@csrf_exempt
def unsave_internship(request, pk):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_id = data.get("userId")

            if not user_id:
                return JsonResponse(
                    {"error": "User ID is required"}, status=status.HTTP_400_BAD_REQUEST
                )

            student_collection.update_one(
                {"_id": ObjectId(user_id)}, {"$pull": {"saved_internships": pk}}
            )

            return JsonResponse({"message": "Internship removed from saved"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
def get_saved_internships(request, user_id):
    try:
        user = student_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return JsonResponse(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        saved_internships = user.get("saved_internships", [])
        internships = []

        for internship_id in saved_internships:
            internship = internship_collection.find_one({"_id": ObjectId(internship_id)})
            if internship:
                internship["_id"] = str(internship["_id"])
                internships.append(internship)
        
        return JsonResponse({"message": "Saved internships retrieved successfully", "internships": internships})
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

# =========================================================================== ACHIEVEMENTS =============================================================================================

@csrf_exempt
@api_view(['POST'])
def post_student_achievement(request):
    """
    Handles submission of student achievements with file uploads.
    """
    # Extract and validate the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith("Bearer "):
        return JsonResponse({"error": "No token provided"}, status=401)

    token = auth_header.split(" ")[1]

    try:
        # Decode the JWT token
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            leeway=timedelta(seconds=300)  # Allow 5 minutes of clock skew
        )
        student_id = payload.get('student_user')
        if not student_id:
            return JsonResponse({"error": "Invalid token"}, status=401)

        # Handle form data (multipart/form-data)
        name = request.POST.get("name")
        achievement_description = request.POST.get("achievement_description")
        achievement_type = request.POST.get("achievement_type")
        company_name = request.POST.get("company_name")
        date_of_achievement = request.POST.get("date_of_achievement")
        batch = request.POST.get("batch")

        # Validate required fields
        required_fields = [
            "name", "achievement_description", "achievement_type",
            "company_name", "date_of_achievement", "batch"
        ]
        for field in required_fields:
            if not locals().get(field):
                return JsonResponse(
                    {"error": f"{field.replace('_', ' ').capitalize()} is required."},
                    status=400
                )

        # Handle file upload
        file_base64 = None
        if "photo" in request.FILES:
            photo = request.FILES["photo"]
            file_base64 = base64.b64encode(photo.read()).decode("utf-8")

        # Prepare the document for MongoDB
        achievement_data = {
            "student_id": student_id,
            "name": name,
            "achievement_description": achievement_description,
            "achievement_type": achievement_type,
            "company_name": company_name,
            "date_of_achievement": date_of_achievement,
            "batch": batch,
            "photo": file_base64,  # Base64-encoded file (optional)
            "is_approved": False,  # Pending approval by default
            "submitted_at": datetime.utcnow(),
        }

        # Insert the document into MongoDB
        achievement_collection.insert_one(achievement_data)

        return JsonResponse(
            {"message": "Achievement submitted successfully. Admin will contact you soon"},
            status=201
        )

    except jwt.ExpiredSignatureError:
        return JsonResponse({"error": "Token expired"}, status=401)
    except jwt.DecodeError:
        return JsonResponse({"error": "Invalid token"}, status=401)
    except Exception as e:
        # Log unexpected errors for debugging
        traceback.print_exc()
        return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)
    
@csrf_exempt
def review_achievement(request, achievement_id):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            action = data.get("action")
            if action not in ["approve", "reject"]:
                return JsonResponse({"error": "Invalid action"}, status=400)

            achievement = achievement_collection.find_one({"_id": ObjectId(achievement_id)})
            if not achievement:
                return JsonResponse({"error": "Achievement not found"}, status=404)

            is_publish = True if action == "approve" else False
            achievement_collection.update_one(
                {"_id": ObjectId(achievement_id)},
                {"$set": {"is_publish": is_publish, "updated_at": datetime.now()}}
            )

            message = "Achievement approved and published successfully" if is_publish else "Achievement rejected successfully"
            return JsonResponse({"message": message}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse({"error": "Invalid request method"}, status=400)

@csrf_exempt
def get_all_study_material(request):
    """
    Fetch a single study material by its ID.
    """
    try:
        study_materials = study_material_collection.find({})
        study_material_list = []
        for material in study_materials:
            material["_id"] = str(material["_id"])  # Convert ObjectId to string
            study_material_list.append(material)

        if not study_material_list:
            return JsonResponse({"error": "Study materials not found"}, status=404)

        return JsonResponse({"study_materials": study_material_list}, status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

@csrf_exempt
def job_click(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            job_id = data.get("job_id")
            job = job_collection.find_one({"_id": ObjectId(job_id)})
            if not job:
                return JsonResponse({"error": "Job not found"}, status=404)

            job_collection.update_one(
                {"_id": ObjectId(job_id)},
                {"$inc": {"clicks": 1}}
            )

            return JsonResponse({"message": "Job click recorded successfully"}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)


#================================================================Applied Jobs================================================================================================


@csrf_exempt
def apply_job(request):
    try:
        data = json.loads(request.body)
        student_id = data.get("studentId")
        job_id = data.get("jobId")

        if not student_id or not job_id:
            return JsonResponse({"error": "Student ID and Job ID are required"}, status=400)

        # Retrieve the student document
        student = student_collection.find_one({"_id": ObjectId(student_id)})
        if not student:
            return JsonResponse({"error": "Student not found"}, status=404)

        applied_jobs = student.get("applied_jobs", [])
        if any(job["job_id"] == str(ObjectId(job_id)) for job in applied_jobs):
            return JsonResponse({"message": "Job already applied"}, status=200)

        # Update the student's applied jobs in the database with confirmation status as null
        result = student_collection.update_one(
            {"_id": ObjectId(student_id)},
            {"$addToSet": {"applied_jobs": {
                "job_id": str(ObjectId(job_id)),  # Convert ObjectId to string
                "confirmed": None  # Set confirmed status to null
            }}}
        )

        if result.modified_count == 0:
            return JsonResponse({"error": "Failed to update applied jobs"}, status=400)

        return JsonResponse({"message": "Job application recorded successfully"})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
def confirm_job(request):
    try:
        data = json.loads(request.body)
        student_id = data.get("studentId")
        job_id = data.get("jobId")
        confirmed = data.get("confirmed")

        if not student_id or not job_id or confirmed is None:
            return JsonResponse({"error": "Student ID, Job ID, and confirmation status are required"}, status=400)

        # Log the received data for debugging
        print(f"Received studentId: {student_id}, jobId: {job_id}, confirmed: {confirmed}")

        # Update the confirmation status of the applied job in the student collection
        result = student_collection.update_one(
            {"_id": ObjectId(student_id), "applied_jobs.job_id": job_id},
            {"$set": {"applied_jobs.$.confirmed": confirmed}}
        )

        # Log the result for debugging
        print(f"Update result in student collection: {result.raw_result}")

        if result.modified_count == 0:
            return JsonResponse({"error": "Failed to update confirmation status. No matching document found."}, status=400)

        # Update the job collection to add the student ID to the applied array
        job_result = job_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$addToSet": {"applied": str(ObjectId(student_id))}}  # Use $addToSet to avoid duplicates
        )

        # Log the result for debugging
        print(f"Update result in job collection: {job_result.raw_result}")

        if job_result.modified_count == 0:
            return JsonResponse({"error": "Failed to update job data. No matching document found."}, status=400)

        return JsonResponse({"message": "Job application status updated successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)

@csrf_exempt
def get_applied_jobs(request, userId):
    try:
        # Find the student by ID
        student = student_collection.find_one({"_id": ObjectId(userId)})

        if not student:
            return JsonResponse({"error": "Student not found"}, status=404)

        # Get the list of applied job IDs
        applied_jobs = student.get("applied_jobs", [])

        return JsonResponse({"jobs": applied_jobs})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)