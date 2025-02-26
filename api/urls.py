from django.urls import path
from .views import *
from .admin_views import *
from .message import * 
from .jobs import *

urlpatterns = [
  
    #admin
    path("admin-signup/", admin_signup, name="admin_signup"),
    path("login/", admin_login, name="admin_login"),
    path("forgot-password/", forgot_password, name="forgot_password"),
    path("reset-password/", reset_password, name="reset_password"),
    path('post-internship/', post_internship, name='post_internship'),
    path('internship/', get_internships, name='get_internships'),
    path("job_post/", job_post, name="job_post"),
    path('manage-jobs/', manage_jobs, name='manage_jobs'),
    path('mailjobs/', get_admin_inbox, name='get_admin_inbox'),
    path('post-study-material/',post_study_material, name="post_study_material"),
    path("manage-internships/", manage_internships, name="manage_internships"),
    path('manage-achievements/',manage_achievements, name="manage_achievements"),
    path('manage-study-materials/',manage_study_materials, name="manage_study_materials" ),
    path('fetch-review/', fetch_review, name='fetch_review'),
    path('get-admin/<str:userId>/', get_admin_details, name='get_admin_details'),
    path('update-admin/<str:userId>/', update_admin_profile, name='update_admin_profile'),
    path("get-categories/", get_categories, name="get_categories"),
    path('topics-by-category/', get_topics_by_category, name='get_topics_by_category'),
    path('materials-by-topic/', get_materials_by_topic, name='get_materials_by_topic'),
    
    #superadmin
    path("superadmin_signup/",super_admin_signup,name= "super_admin_signup"),
    path("superadmin_login/",super_admin_login,name="super_admin_login"),
    path('get-superadmin/<str:userId>/', get_superadmin_details, name='get_superadmin_details'),
    path('update-superadmin/<str:userId>/', update_superadmin_profile, name='update_superadmin_profile'),
    path("get-contact-messages/",get_contact_messages,name="get_contact_messages"),
    path('reply_to_message/',reply_to_message,name="reply_to_message"),
    path("toggle-auto-approval/",toggle_auto_approval, name="toggle_auto_approval"),
    path("get-auto-approval-status/",get_auto_approval_status, name="get_auto_approval_status"),
    path('admin-status/<str:id>/', admin_status_update, name='admin_status_update'),
    path('get_jobs_with_admin/',get_jobs_with_admin, name="get_jobs_with_admin"),
    path("get_achievements_with_admin/", get_achievements_with_admin, name="get_achievements_with_admin"),
    path("get_internships_with_admin/", get_internships_with_admin, name="get_internships_with_admin"),
    path("get_study_materials_with_admin/", get_study_materials_with_admin, name="get_study_materials_with_admin"),
    path("get_student_achievements_with_students/", get_student_achievements, name="get_student_achievements_with_students"),
    path('all-jobs-internships/', get_all_jobs_and_internships, name='all_jobs_internships'),
    path('mark_messages_as_seen/<str:student_id>/', mark_messages_as_seen_by_admin, name='mark_messages_as_seen'),
    

    
    #account management 
    path('students/', get_students, name='get_students'),
    path('students/<str:student_id>/update/', update_student, name='update_student'),
    path('students/<str:student_id>/delete/', delete_student, name='delete_student'), 
    path("admins-list/", get_admin_list, name="get_admins_list"),
    path('admin-details/<str:id>/', admin_details, name='admin-details'),
    path('admin/<str:id>/edit/', edit_admin_details, name='edit_admin_details'),

    #common
    path("forgot-password/", forgot_password, name="forgot_password"),
    path("reset-password/", reset_password, name="reset_password"),
    path("verify-otp/", verify_otp, name="verify_otp"),

    
    #Jobs
    path('jobs', get_jobs_for_mail, name='get_jobs'),
    path('upload_job_image/', upload_job_image, name='upload_job_image'),
    path("review-job/<str:job_id>/", review_job, name="approve_job"),
    path('job/<str:job_id>/', get_job_by_id, name='get_job_by_id'),
    path('job-edit/<str:job_id>/', update_job, name='update_job'),
    path('job-delete/<str:job_id>/', delete_job, name='delete_job'),
    path('get-jobs/', get_jobs, name='get_jobs'),
    path('submit-feedback/', submit_feedback, name='submit_feedback'),
    path('apply-job/', apply_job, name='apply_job'),
    path('confirm-job/', confirm_job, name='confirm_job'),
    path('applied-jobs/<str:userId>/', get_applied_jobs, name='get_applied_jobs'),
    

    #Achievements
    path("upload_achievement/",post_achievement,name="upload_achievement"),
    path('achievements/', get_achievements, name='get_achievements'),
    path('edit-achievement/<str:achievement_id>/', update_achievement, name='edit-achievement'),
    path('delete-achievement/<str:achievement_id>/', delete_achievement, name='delete_achievement'),
    path("achievement/<str:achievement_id>/",get_achievement_by_id,name="get_achievement_by_id"),
    # path('review-achievement/<str:achievement_id>/', review_achievement, name='review_achievement'),
    path('published-achievement/', get_published_achievements, name='get_published_achievements'),
    path('get-achievement/<str:achievement_id>/', achievement_detail, name='achievement_detail'),
    path("studentachievement/", post_student_achievement, name="get_student_achievements"),
    
    #Internships
    path('internship/', get_internships, name='get_internship'),
    path('review-internship/<str:internship_id>/', review_internship, name='review_internship'),
    path("upload-internship-image/", upload_internship_image, name="upload_internship_image"),
    path('internship/<str:internship_id>/', get_internship_id, name='get_internship'),
    path('internship-edit/<str:internship_id>/', update_internship, name='update_internship'),
    path('internship-delete/<str:internship_id>/', delete_internship, name='delete_internship'),
    path("save-internship/<str:pk>/", save_internship, name="save-job"),
    path("unsave-internship/<str:pk>/", unsave_internship, name="unsave-job"),
    path("saved-internships/<str:user_id>/", get_saved_internships, name="get-saved-jobs"),
    
    #student
    path("student-signup/", student_signup, name="student_signup"),
    path("stud/login/", student_login, name="student_login"),
    path("profile/<str:userId>/", get_profile, name="get_profile"),
    path('update-profile/<str:userId>/', update_profile, name='update_profile'),
    path('student-forgot-password/', student_forgot_password, name='student_forgot_password'),
    path('student-verify-otp/', student_verify_otp, name='student_verify_otp'),
    path('student-reset-password/', student_reset_password, name='student_reset_password'),
    path('published-jobs/', get_published_jobs, name='get_published_jobs'),
    path('published-internship/', get_published_internships, name='get_published_internships'),
    # path("contact-us/",contact_us,name="contact-us"),
    path("save-job/<str:pk>/", save_job, name="save-job"),
    path("unsave-job/<str:pk>/", unsave_job, name="unsave-job"),
    path("saved-jobs/<str:user_id>/", get_saved_jobs, name="get-saved-jobs"),
    # path("get_student_messages/", get_student_messages, name="get_student_messages"),
    path("mark_messages_as_seen_by_student/<str:student_id>/", mark_messages_as_seen_by_student, name="mark_messages_as_seen"),


    #study_material
    path("study-material/<str:study_material_id>/", get_study_material_by_id, name="get_study_material_by_id"),
    path("study-material-edit/<str:study_material_id>/", update_study_material, name="update_study_material"),
    path("study-material-delete/<str:study_material_id>/", delete_study_material, name="delete_study_material"),
    path("all-study-material/", get_all_study_material, name="get_all_study_material"),
    path("get-categories/", get_categories, name="get_categories"),
    

    #contact-us
    path('contact-us/', contact_us, name='contact_us'),
    path("get_student_messages/<student_id>/", get_student_messages, name="get_student_messages"),
    path('student_send_message/', student_send_message, name='student_send_message'),
    path('get_all_student_chats/', get_all_student_chats, name='get_all_student_chats'),
    path('admin_reply_message/', admin_reply_message, name='admin_reply_message'),

    #test
    path("test_job_post/", test_job_post, name="test_job_post"),

    #view count
     path('viewcount/<str:id>/', view_count, name='view_count'),

     #Jobs
    path('fetch-jobs-api/', fetch_jobs_api, name='fetch-jobs-api'),
    path('scrape-naukri-jobs/', scrape_naukri_jobs, name='scrape-indeed-jobs'),
    path('search-jobs/', search_jobs, name='search-jobs'),
]
