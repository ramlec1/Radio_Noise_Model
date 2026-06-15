from flask import Flask


def create_app():
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY='your_secret_key',
    )

    from .routes.main import main_bp
    from .routes.search import search_bp
    from .routes.simulate import simulate_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(simulate_bp)

    return app
