# Guide de Contribution

Merci de contribuer au Wheel Trading Bot ! Voici les guidelines à suivre.

## 🚀 Setup du Développement

1. **Clone le repository**

```bash
git clone <repository-url>
cd wheel-trading-bot
```

2. **Setup de l'environnement**

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows
```

3. **Install les dépendances**

```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
```

4. **Setup la configuration**

```bash
cp .env.example .env
```

## 📝 Code Style

Le projet utilise les outils suivants :

- **Black** pour le formatage (ligne max: 100 caractères)
- **isort** pour l'organisation des imports
- **mypy** pour la vérification de types
- **flake8** pour le linting

Avant de commiter, formatte ton code :

```bash
# Format le code
black . --line-length=100
isort .

# Check le linting
flake8 . --max-line-length=100
mypy . --ignore-missing-imports
```

## 🧪 Tests

Tous les changements doivent être testés.

```bash
# Run les tests
pytest tests/ -v

# Avec coverage
pytest tests/ -v --cov=.
```

## 📋 Type Hints

Ajoute des type hints à tous les nouveaux codes :

```python
def ma_fonction(param: str) -> Dict[str, Any]:
    """Description de la fonction."""
    pass
```

## 📚 Documentation

- Ajoute des docstrings à toutes les fonctions/classes
- Utilise le format Google style docstrings :

```python
def ma_fonction(param1: str, param2: int) -> bool:
    """Brève description.

    Description plus longue si nécessaire.

    Args:
        param1: Description du paramètre 1
        param2: Description du paramètre 2

    Returns:
        Description du retour

    Raises:
        ValueError: Description de l'exception
    """
    pass
```

## 🔒 Sécurité

- Jamais de secrets ou API keys dans le code
- Utilise `.env.example` pour les configurations
- Valide tous les inputs utilisateur
- Ajoute la gestion d'erreurs appropriée

## 🎯 Commits

Format des messages de commit :

```
<type>(<scope>): <subject>

<body>
```

Types :

- `feat`: Nouvelle fonctionnalité
- `fix`: Correction de bug
- `refactor`: Refactorisation de code
- `test`: Ajout de tests
- `docs`: Modification de documentation
- `style`: Changements de formatting

Exemple :

```
feat(scanner): Add IV filtering for put options

- Add minimum IV check in scanner
- Update config with MIN_IV parameter
- Add tests for IV validation
```

## 🔄 Pull Requests

1. Crée une branche pour ta feature

```bash
git checkout -b feat/ma-nouvelle-feature
```

2. Fais tes changements et teste
3. Commite avec des messages clairs
4. Push ta branche
5. Ouvre une PR avec description claire

## ❓ Questions

N'hésite pas à ouvrir une issue si tu as des questions !
