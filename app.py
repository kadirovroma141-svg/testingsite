import os
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

from config import get_config
from models import db, User

login_manager = LoginManager()
migrate = Migrate()


def create_app(config=None) -> Flask:
    app = Flask(__name__)

    # ------------------------------------------------------------------ config
    cfg = config or get_config()
    app.config.from_object(cfg)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # ------------------------------------------------------------ extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Пожалуйста, войдите в систему."
    login_manager.login_message_category = "warning"

    # ------------------------------------------------------- user loader
    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # --------------------------------------------------------- blueprints
    from blueprints.auth    import auth_bp
    from blueprints.admin   import admin_bp
    from blueprints.teacher import teacher_bp
    from blueprints.student import student_bp
    from blueprints.api     import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp,   url_prefix="/admin")
    app.register_blueprint(teacher_bp, url_prefix="/teacher")
    app.register_blueprint(student_bp)
    app.register_blueprint(api_bp,     url_prefix="/api")

    # ------------------------------------------------- create tables (dev)
    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True, port=5001)
