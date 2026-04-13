import os
import uuid
import datetime
import json
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import stripe
import requests

# ==================== CONFIGURATION ====================

app = Flask(__name__,
    template_folder='../templates',
    static_folder='../static'
)

# === CORRECTION POUR RENDER (SQLite dans /tmp) ===
db_path = os.path.join('/tmp', 'kisetigi.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
# ====================================================

app.config['SECRET_KEY'] = 'changez-moi-ici-123456789'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'jwt-secret-changez-moi-987654321'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'

# Stripe (test mode - remplacez par vos clés plus tard)
stripe.api_key = 'sk_test_votre_cle'

# Agora (remplacez par votre App ID)
AGORA_APP_ID = 'votre_app_id_agora'

db = SQLAlchemy(app)
jwt = JWTManager(app)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Admin panel
admin = Admin(app, name='Kise Tigi Admin', template_mode='bootstrap4')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('../uploads', exist_ok=True)

# ==================== MODÈLES ====================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, default='')
    avatar_url = db.Column(db.String(500), default='')
    role = db.Column(db.String(20), default='user')
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    balance = db.Column(db.Float, default=0.0)
    followers_count = db.Column(db.Integer, default=0)
    following_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'bio': self.bio,
            'avatar_url': self.avatar_url,
            'role': self.role,
            'is_verified': self.is_verified,
            'balance': self.balance,
            'followers_count': self.followers_count,
            'following_count': self.following_count,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Video(db.Model):
    __tablename__ = 'videos'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    video_url = db.Column(db.String(500), nullable=False)
    thumbnail_url = db.Column(db.String(500))
    duration = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    likes_count = db.Column(db.Integer, default=0)
    comments_count = db.Column(db.Integer, default=0)
    shares_count = db.Column(db.Integer, default=0)
    is_live = db.Column(db.Boolean, default=False)
    is_shoppable = db.Column(db.Boolean, default=False)
    price = db.Column(db.Float, default=0.0)
    is_private = db.Column(db.Boolean, default=False)   # nécessaire pour d'éventuels filtres
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    user = db.relationship('User', backref='videos')

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.to_dict() if self.user else None,
            'title': self.title,
            'description': self.description,
            'video_url': self.video_url,
            'thumbnail_url': self.thumbnail_url,
            'views': self.views,
            'likes_count': self.likes_count,
            'is_live': self.is_live,
            'is_shoppable': self.is_shoppable,
            'price': self.price,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    seller_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='EUR')
    image_url = db.Column(db.String(500))
    stock = db.Column(db.Integer, default=1)
    category = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    seller = db.relationship('User', backref='products')

    def to_dict(self):
        return {
            'id': self.id,
            'seller': self.seller.to_dict() if self.seller else None,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'currency': self.currency,
            'image_url': self.image_url,
            'stock': self.stock,
            'category': self.category
        }

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')
    stripe_payment_id = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    buyer = db.relationship('User', foreign_keys=[buyer_id])
    product = db.relationship('Product')

    def to_dict(self):
        return {
            'id': self.id,
            'buyer': self.buyer.to_dict() if self.buyer else None,
            'product': self.product.to_dict() if self.product else None,
            'quantity': self.quantity,
            'total_price': self.total_price,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text)
    attachment_url = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

    def to_dict(self):
        return {
            'id': self.id,
            'sender': self.sender.to_dict() if self.sender else None,
            'receiver': self.receiver.to_dict() if self.receiver else None,
            'content': self.content,
            'attachment_url': self.attachment_url,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class LiveStream(db.Model):
    __tablename__ = 'live_streams'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    agora_channel = db.Column(db.String(100), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    viewers_count = db.Column(db.Integer, default=0)
    donations_amount = db.Column(db.Float, default=0.0)
    started_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    ended_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='live_streams')

    def to_dict(self):
        return {
            'id': self.id,
            'user': self.user.to_dict() if self.user else None,
            'title': self.title,
            'agora_channel': self.agora_channel,
            'is_active': self.is_active,
            'viewers_count': self.viewers_count,
            'donations_amount': self.donations_amount,
            'started_at': self.started_at.isoformat() if self.started_at else None
        }

# ==================== CRÉATION DES TABLES (EXÉCUTÉ À CHAQUE DÉMARRAGE) ====================
with app.app_context():
    db.create_all()
    print("✅ Base de données vérifiée/créée")

# ==================== ADMIN VIEWS ====================

class AdminModelView(ModelView):
    def is_accessible(self):
        return True

class UserAdmin(AdminModelView):
    column_list = ['username', 'email', 'role', 'is_active', 'balance', 'created_at']
    column_searchable_list = ['username', 'email']

class VideoAdmin(AdminModelView):
    column_list = ['title', 'user', 'views', 'likes_count', 'is_live', 'created_at']

class ProductAdmin(AdminModelView):
    column_list = ['name', 'seller', 'price', 'stock', 'category']

class OrderAdmin(AdminModelView):
    column_list = ['id', 'buyer', 'product', 'total_price', 'status']

admin.add_view(UserAdmin(User, db.session))
admin.add_view(VideoAdmin(Video, db.session))
admin.add_view(ProductAdmin(Product, db.session))
admin.add_view(OrderAdmin(Order, db.session))

# ==================== ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin-panel')
def admin_panel():
    stats = {
        'total_users': User.query.count(),
        'total_videos': Video.query.count(),
        'total_products': Product.query.count(),
        'total_orders': Order.query.count(),
        'total_revenue': db.session.query(db.func.sum(Order.total_price)).scalar() or 0,
        'active_lives': LiveStream.query.filter_by(is_active=True).count()
    }
    return render_template('admin_dashboard.html', stats=stats)

# ==================== API ROUTES ====================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Nom d\'utilisateur déjà pris'}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email déjà utilisé'}), 400
    user = User(username=data['username'], email=data['email'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    if User.query.count() == 1:
        user.role = 'admin'
        db.session.commit()
    token = create_access_token(identity=user.id)
    return jsonify({'user': user.to_dict(), 'access_token': token}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Identifiants invalides'}), 401
    token = create_access_token(identity=user.id)
    return jsonify({'user': user.to_dict(), 'access_token': token})

@app.route('/api/videos/upload', methods=['POST'])
@jwt_required()
def upload_video():
    user_id = get_jwt_identity()
    if 'video' not in request.files:
        return jsonify({'error': 'Aucune vidéo'}), 400
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    video = Video(
        user_id=user_id,
        title=request.form.get('title', 'Sans titre'),
        description=request.form.get('description', ''),
        video_url=f'/uploads/{filename}'
    )
    db.session.add(video)
    db.session.commit()
    return jsonify(video.to_dict())

@app.route('/api/videos', methods=['GET'])
def get_videos():
    videos = Video.query.filter_by(is_live=False).order_by(Video.created_at.desc()).limit(50).all()
    return jsonify({'videos': [v.to_dict() for v in videos]})

@app.route('/api/videos/<video_id>/like', methods=['POST'])
@jwt_required()
def like_video(video_id):
    user_id = get_jwt_identity()
    video = Video.query.get_or_404(video_id)
    video.likes_count += 1
    db.session.commit()
    socketio.emit('like_update', {'video_id': video_id, 'likes_count': video.likes_count, 'user_id': user_id, 'action': 'liked'}, room=f'video_{video_id}')
    return jsonify({'action': 'liked', 'likes_count': video.likes_count})

@app.route('/api/videos/<video_id>/comments', methods=['GET'])
def get_comments(video_id):
    return jsonify({'comments': []})

@app.route('/api/videos/<video_id>/comments', methods=['POST'])
@jwt_required()
def add_comment(video_id):
    data = request.get_json()
    return jsonify({'message': 'Commentaire ajouté'}), 201

@app.route('/api/products', methods=['GET'])
def get_products():
    products = Product.query.filter_by(is_active=True).all()
    return jsonify({'products': [p.to_dict() for p in products]})

@app.route('/api/products', methods=['POST'])
@jwt_required()
def create_product():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if user.role not in ['admin', 'verified_seller']:
        return jsonify({'error': 'Non autorisé'}), 403
    data = request.get_json()
    product = Product(
        seller_id=user_id,
        name=data['name'],
        description=data.get('description', ''),
        price=data['price'],
        category=data.get('category', '')
    )
    db.session.add(product)
    db.session.commit()
    return jsonify(product.to_dict())

@app.route('/api/messages/send', methods=['POST'])
@jwt_required()
def send_message():
    sender_id = get_jwt_identity()
    data = request.get_json()
    msg = Message(
        sender_id=sender_id,
        receiver_id=data['receiver_id'],
        content=data['content']
    )
    db.session.add(msg)
    db.session.commit()
    socketio.emit('new_message', msg.to_dict(), room=f"user_{data['receiver_id']}")
    return jsonify(msg.to_dict())

@app.route('/api/live/start', methods=['POST'])
@jwt_required()
def start_live():
    user_id = get_jwt_identity()
    data = request.get_json()
    channel = f"live_{uuid.uuid4().hex[:8]}"
    live = LiveStream(
        user_id=user_id,
        title=data['title'],
        agora_channel=channel
    )
    db.session.add(live)
    db.session.commit()
    token = f"token_{channel}"
    return jsonify({
        'live': live.to_dict(),
        'agora_app_id': AGORA_APP_ID,
        'agora_token': token,
        'channel': channel
    })

# ==================== ROUTES FEED ET LIVE ====================

@app.route('/api/feed/for-you', methods=['GET'])
def for_you_feed():
    videos = Video.query.filter_by(is_live=False).order_by(Video.created_at.desc()).limit(20).all()
    return jsonify({'videos': [v.to_dict() for v in videos]})

@app.route('/api/feed/nearby', methods=['GET'])
def nearby_feed():
    videos = Video.query.filter_by(is_live=False).order_by(Video.created_at.desc()).limit(20).all()
    return jsonify({'videos': [v.to_dict() for v in videos]})

@app.route('/api/live/active', methods=['GET'])
def get_active_lives():
    lives = LiveStream.query.filter_by(is_active=True).all()
    return jsonify({'lives': [l.to_dict() for l in lives]})

# ==================== SOCKET.IO ====================

@socketio.on('join_live')
def handle_join_live(data):
    live_id = data['live_id']
    join_room(f'live_{live_id}')
    live = LiveStream.query.get(live_id)
    if live:
        live.viewers_count += 1
        db.session.commit()
        emit('viewer_update', {'count': live.viewers_count}, room=f'live_{live_id}')

@socketio.on('live_comment')
def handle_live_comment(data):
    emit('new_live_comment', data, room=f"live_{data['live_id']}")

# ==================== LANCEMENT (pour exécution locale) ====================
if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)