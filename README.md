# Wheel Trading Bot

Un bot de trading automatisé implémentant la stratégie du wheel (covered calls + cash-secured puts) pour le trading d'options.

## 🎯 Fonctionnalités

- **Scanning de symboles** : Analyse les actions pour identifier les opportunités de trading
- **Stratégie Wheel** : Rotation entre puts sécurisés en espèces et calls couverts sur la même action
- **API Backend** : API REST pour consulter les scans, gérer l'historique et surveiller les positions
- **Base de données** : Persistance des données avec SQLAlchemy ORM
- **Frontend** : Interface web pour visualiser les données et les positions
- **Market Data** : Module de récupération des données financières (yfinance) - à intégrer

## � Installation

### Prérequis

- Python 3.10+
- Node.js (pour le frontend)

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# ou .venv\Scripts\activate  # Windows

pip install -r requirements-dev.txt
cd backend && pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## ⚙️ Configuration

Créer un fichier `.env` basé sur `.env.example` :

```bash
cp .env.example .env
```

**Variables importantes :**

- `DATABASE_URL` : URL de la base de données (SQLite par défaut)
- `CORS_ORIGINS` : Origines autorisées (ex: `http://localhost:5173`)
- `LOG_LEVEL` : Niveau de logging (`INFO`, `DEBUG`, etc.)

## 🏃 Utilisation

### Développement

```bash
# Backend (terminal 1)
cd backend && python main.py

# Frontend (terminal 2)
cd frontend && npm run dev

# Scanner (terminal 3)
cd backend && python main_scan.py
```

### Production

```bash
docker-compose up --build
```

## 📁 Structure du projet

```
wheel-trading-bot/
├── backend/              # API REST (FastAPI)
│   ├── main.py          # Serveur FastAPI
│   ├── main_scan.py     # Scanner de trading
│   ├── database.py      # Modèles SQLAlchemy
│   ├── schemas.py       # Schémas Pydantic
│   ├── config.py        # Configuration DB
│   └── requirements.txt # Dépendances
├── frontend/            # Interface (React + Vite)
│   ├── src/App.jsx      # Application principale
│   ├── package.json     # Dépendances npm
│   └── Dockerfile       # Containerisation
├── .env.example         # Configuration template
├── docker-compose.yml   # Orchestration
└── pyproject.toml       # Configuration Python
```

## 🧪 Développement

### Tests

```bash
# ⚠️ À implémenter dans backend/tests/
pytest backend/tests/ -v --cov=backend
```

### Qualité du code

```bash
# Linting
flake8 . --max-line-length=100

# Type checking
mypy . --ignore-missing-imports

# Formatage
black . --line-length=100
isort .
```

## 🔧 Dépendances

### Backend

- **FastAPI** : Framework API
- **SQLAlchemy** : ORM base de données
- **yfinance** : Données financières
- **pandas** : Analyse de données

### Frontend

- **React 19** : Framework UI
- **Vite** : Bundler de développement

### Développement

- **pytest** : Tests unitaires
- **black** : Formatage
- **mypy** : Vérification de types
- **flake8** : Linting

## 🔒 Sécurité

- ✅ CORS restreint aux origines configurées
- ✅ Gestion robuste des erreurs
- ✅ Logging structuré
- ✅ Type hints pour la sécurité des types
- ⚠️ Authentification à implémenter
- ⚠️ Rate limiting à implémenter

## 📊 Résultats

Les scans sont sauvegardés dans `scan_results_[DATE]_[HEURE].csv`

## 📚 Documentation

- **PROJECT_STRUCTURE.md** : Structure détaillée du projet
- **CONTRIBUTING.md** : Guide de contribution
- **CHANGES.md** : Historique des changements

## 📝 Licence

À définir

## 👨‍💻 Auteur

Projet personnel de trading automatisé
