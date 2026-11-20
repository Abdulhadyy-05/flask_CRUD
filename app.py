import os
from datetime import timedelta, datetime

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
)
from werkzeug.security import generate_password_hash, check_password_hash
from flasgger import Swagger

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'postgresql://postgres:admin321@localhost/first_db'
)
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'change-me-in-production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=2)

# Adds the "Authorize" button in Swagger UI
swagger_template = {
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Type: Bearer <your_token>",
        }
    },
    "security": [{"Bearer": []}],
}
Swagger(app, template=swagger_template)

db = SQLAlchemy(app)
jwt = JWTManager(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'email': self.email}


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'user_id': self.user_id,
        }


class TokenBlocklist(db.Model):
    """Stores tokens that were logged out."""
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


@jwt.token_in_blocklist_loader
def is_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    return TokenBlocklist.query.filter_by(jti=jti).first() is not None


@jwt.revoked_token_loader
def revoked_token_response(jwt_header, jwt_payload):
    return jsonify({'error': 'token has been revoked, please log in again'}), 401


with app.app_context():
    db.create_all()


# ---------- AUTH (public) ----------

@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}
    name, email, password = data.get('name'), data.get('email'), data.get('password')

    if not name or not email or not password:
        return jsonify({'error': 'name, email and password are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'password must be at least 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'email already registered'}), 409

    user = User(name=name, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({'user': user.to_dict(), 'access_token': token}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email, password = data.get('email'), data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password or ''):
        return jsonify({'error': 'invalid email or password'}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({'user': user.to_dict(), 'access_token': token}), 200


@app.route("/api/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    db.session.add(TokenBlocklist(jti=jti))
    db.session.commit()
    return jsonify({'message': 'logged out successfully'}), 200


# ---------- USERS (protected) ----------

@app.route("/api/users", methods=["GET"])
@jwt_required()
def get_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route("/api/users/<int:user_id>", methods=["GET"])
@jwt_required()
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict()), 200


@app.route("/api/users/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_user(user_id):
    if int(get_jwt_identity()) != user_id:
        return jsonify({'error': 'you can only update your own account'}), 403
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    user.name = data.get('name', user.name)
    user.email = data.get('email', user.email)
    if data.get('password'):
        user.set_password(data['password'])
    db.session.commit()
    return jsonify(user.to_dict()), 200


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    if int(get_jwt_identity()) != user_id:
        return jsonify({'error': 'you can only delete your own account'}), 403
    user = User.query.get_or_404(user_id)
    Post.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted successfully'}), 200


# ---------- POSTS (protected) ----------

@app.route("/api/posts", methods=["POST"])
@jwt_required()
def create_post():
    data = request.get_json() or {}
    if not data.get('title') or not data.get('content'):
        return jsonify({'error': 'title and content are required'}), 400
    post = Post(
        title=data['title'],
        content=data['content'],
        user_id=int(get_jwt_identity()),  # taken from the token
    )
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_dict()), 201


@app.route("/api/posts/<int:post_id>", methods=["GET"])
@jwt_required()
def get_post(post_id):
    post = Post.query.get_or_404(post_id)
    return jsonify(post.to_dict()), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True) 