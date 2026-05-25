from blueprints.auth    import auth_bp
from blueprints.admin   import admin_bp
from blueprints.teacher import teacher_bp
from blueprints.student import student_bp
from blueprints.api     import api_bp

__all__ = ["auth_bp", "admin_bp", "teacher_bp", "student_bp", "api_bp"]
