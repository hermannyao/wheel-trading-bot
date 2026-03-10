# 📁 Structure du Projet - Wheel Trading Bot

## Vue d'ensemble

Le projet est organisé en deux parties distinctes : **Backend (FastAPI)** et **Frontend (React + Vite)**.

```
wheel-trading-bot/
├── backend/                 # API REST et logique métier
│   ├── main.py             # Point d'entrée FastAPI
│   ├── main_scan.py        # Scanner de trading
│   ├── database.py         # Modèles de données SQLAlchemy
│   ├── schemas.py          # Schémas Pydantic
│   ├── config.py           # Configuration DB
│   ├── logging_config.py   # Configuration logging
│   └── requirements.txt    # Dépendances backend
│
├── frontend/               # Interface utilisateur
│   ├── src/
│   │   ├── App.jsx         # Composant principal
│   │   ├── main.jsx        # Point d'entrée
│   │   └── assets/         # Ressources statiques
│   ├── public/             # Fichiers publics
│   ├── vite.config.js      # Configuration Vite
│   ├── package.json        # Dépendances npm
│   └── Dockerfile          # Containerisation frontend
│
├── .venv/                  # Environnement virtuel Python
├── .vscode/                # Configuration VS Code
│
├── .env.example            # Exemple de configuration
├── .gitignore              # Fichiers à ignorer
├── .dockerignore           # Fichiers à ignorer Docker
│
├── docker-compose.yml      # Orchestration services
├── Dockerfile              # Containerisation backend
│
├── README.md               # Documentation principale
├── CONTRIBUTING.md         # Guide de contribution
├── CHANGES.md              # Historique des changements
├── PROJECT_STRUCTURE.md    # Ce fichier
│
├── pyproject.toml          # Configuration projet Python
├── requirements-dev.txt    # Dépendances développement
├── clean.sh                # Script de nettoyage
│
└── .env                    # Configuration locale (à créer)
```

## Organisation Logique

### Backend (`/backend`)

- **Responsabilités** : API REST, logique métier, base de données, scanning
- **Framework** : FastAPI
- **ORM** : SQLAlchemy
- **Entrée** : `main.py` (pour lancer le serveur)

### Frontend (`/frontend`)

- **Responsabilités** : Interface utilisateur, affichage des données
- **Framework** : React 19
- **Bundler** : Vite
- **Entrée** : `src/main.jsx`

## 🗑️ Code Mort Supprimé

Suite à la réorganisation, les fichiers suivants ont été supprimés de la racine :

```
❌ Supprimés:
  - main.py              → Backend/main.py
  - config.py            → Backend/config.py
  - scanner.py           → Backend/main_scan.py
  - requirements.txt     → Backend/requirements.txt
  - data/                → Intégré au backend
  - market/              → Intégré au backend
  - strategy/            → Intégré au backend
  - tests/               → Code mort (tester dans backend/tests/ si nécessaire)
  - pyvenv.cfg           → Résidu venv
  - clean.sh             → Script supprimé (nettoyage manuel)
```

## 📍 Points d'Entrée

### Pour lancer le développement

```bash
# Backend
cd backend && python main.py

# Frontend
cd frontend && npm run dev

# Ou avec Docker
docker-compose up
```

### Avec VS Code

Utiliser les configurations de debug dans `.vscode/launch.json` :

- `Python: Backend` - Lance FastAPI en mode debug
- `Python: Scanner` - Lance le scanner

## 📦 Dépendances

### Backend

- **Fichier** : `backend/requirements.txt`
- **Installées** : FastAPI, SQLAlchemy, yfinance, pandas, etc.

### Frontend

- **Fichier** : `frontend/package.json`
- **Installées** : React, React-DOM, Vite

### Développement

- **Fichier** : `requirements-dev.txt`
- **Installées** : pytest, black, mypy, flake8, etc.

## 🔧 Configuration

### Variables d'environnement

Créer un fichier `.env` basé sur `.env.example` :

```bash
cp .env.example .env
```

### Configuration Backend

- Base de données : `.env` → `DATABASE_URL`
- Logging : `.env` → `LOG_LEVEL`
- CORS : `.env` → `CORS_ORIGINS`

### Configuration Frontend

- API URL : `frontend/.env` → `VITE_API_BASE_URL`

## 📚 Documentation Supplémentaire

- **README.md** : Vue d'ensemble et installation
- **CONTRIBUTING.md** : Guide de contribution et standards de code
- **CHANGES.md** : Historique des changements récents
