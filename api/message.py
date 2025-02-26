from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from datetime import datetime, timezone
import jwt
from bson import ObjectId
from pymongo import MongoClient

# MongoDB Connection
client = MongoClient("mongodb+srv://ihub:ihub@cce.ksniz.mongodb.net/")  # Replace with your actual MongoDB connection
db = client["CCE"]
message_collection = db["message"]


# JWT Secret Key
JWT_SECRET = "secret"
JWT_ALGORITHM = "HS256"

@csrf_exempt
def contact_us(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            student_id = data.get("student_id")
            student_email = data.get("student_email")  
            content = data.get("message")

            if not all([student_id, student_email, content]):
                return JsonResponse({"error": "All fields are required"}, status=400)

            chat = message_collection.find_one({"student_id": student_id})

            message_entry = {
                "sender": "student",
                "content": content,
                "timestamp": datetime.now(),
                "status": "sent"
            }

            if chat:
                message_collection.update_one(
                    {"student_id": student_id},
                    {"$push": {"messages": message_entry}}
                )
            else:
                new_chat = {
                    "student_id": student_id,
                    "student_email": student_email,
                    "messages": [message_entry]
                }
                message_collection.insert_one(new_chat)

            return JsonResponse({"message": "Message sent successfully!"}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@csrf_exempt
def get_student_messages(request, student_id):
    if request.method == "GET":
        try:
            # 🔹 Extract JWT from Authorization header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JsonResponse({"error": "No token provided"}, status=401)

            token = auth_header.split("Bearer ")[1]  # Extract token

            try:
                decoded_token = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                student_user = decoded_token.get("student_user", None)
                superadmin_id = decoded_token.get("superadmin_user", None)  # ✅ Fix: Use `superadmin_user`

                # ✅ Fix: Allow SuperAdmin or the correct student to access messages
                if superadmin_id or (student_user == student_id):
                    pass  # Authorization successful
                else:
                    return JsonResponse({"error": "Unauthorized access"}, status=403)

            except jwt.ExpiredSignatureError:
                return JsonResponse({"error": "Token expired"}, status=401)
            except jwt.InvalidTokenError:
                return JsonResponse({"error": "Invalid token"}, status=401)

            # 🔹 Fetch messages
            chat = message_collection.find_one({"student_id": str(student_id)}, {"_id": 0, "messages": 1})

            if not chat:
                return JsonResponse({"messages": []}, status=200)

            return JsonResponse({"messages": chat.get("messages", [])}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@csrf_exempt
def student_send_message(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            student_id = data.get("student_id")
            content = data.get("content")

            if not all([student_id, content]):
                return JsonResponse({"error": "All fields are required"}, status=400)

            message_entry = {
                "sender": "student",
                "content": content,
                "timestamp": datetime.now(),
                "status": "sent"
            }

            result = message_collection.update_one(
                {"student_id": student_id},
                {"$push": {"messages": message_entry}}
            )

            if result.modified_count == 0:
                return JsonResponse({"error": "Chat not found"}, status=404)

            return JsonResponse({"message": "Message sent successfully!"}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@csrf_exempt
def get_all_student_chats(request):
    if request.method == "GET":
        try:
            chats = list(message_collection.find({}, {"_id": 1, "student_id": 1, "student_email": 1}))

            for chat in chats:
                chat["_id"] = str(chat["_id"])

            return JsonResponse({"chats": chats}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

@csrf_exempt
def admin_reply_message(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            student_id = data.get("student_id")
            content = data.get("content")

            if not all([student_id, content]):
                return JsonResponse({"error": "All fields are required"}, status=400)

            message_entry = {
                "sender": "admin",
                "content": content,
                "timestamp": datetime.now(),
                "status": "sent"
            }

            result = message_collection.update_one(
                {"student_id": student_id},
                {"$push": {"messages": message_entry}}
            )

            if result.modified_count == 0:
                return JsonResponse({"error": "Chat not found"}, status=404)

            return JsonResponse({"message": "Reply sent successfully!"}, status=200)

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


@csrf_exempt
def mark_messages_as_seen_by_admin(request, student_id):
    if request.method == 'POST':
        try:
            # Find the student's chat document
            student_chat = message_collection.find_one({"student_id": student_id})

            if student_chat:
                # Update the status of all messages to "seen"
                for message in student_chat.get("messages", []):
                    if message["sender"] == "student" and message["status"] == "sent":
                        message["status"] = "seen"

                # Update the document in the database
                message_collection.update_one(
                    {"_id": ObjectId(student_chat["_id"])},
                    {"$set": {"messages": student_chat["messages"]}}
                )

                return JsonResponse({"message": "Messages marked as seen."}, status=200)
            else:
                return JsonResponse({"error": "Student chat not found."}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid request method."}, status=405)
    
@csrf_exempt
def mark_messages_as_seen_by_student(request, student_id):
    if request.method == 'POST':
        try:
            # Find the student's chat document
            student_chat = message_collection.find_one({"student_id": student_id})

            if student_chat:
                # Update the status of all messages from admin to "seen"
                for message in student_chat.get("messages", []):
                    if message["sender"] == "admin" and message["status"] == "sent":
                        message["status"] = "seen"

                # Update the document in the database
                message_collection.update_one(
                    {"_id": ObjectId(student_chat["_id"])},
                    {"$set": {"messages": student_chat["messages"]}}
                )

                return JsonResponse({"message": "Messages marked as seen."}, status=200)
            else:
                return JsonResponse({"error": "Student chat not found."}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    else:
        return JsonResponse({"error": "Invalid request method."}, status=405)