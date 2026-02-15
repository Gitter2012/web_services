Installation Guide
==================

Prerequisites
-------------

- Python 3.10 or higher
- MySQL 8.0 or higher
- Redis (optional, for caching)
- Milvus 2.3+ (optional, for vector embeddings)
- Ollama (optional, for local AI inference)

Quick Start
-----------

1. Clone the Repository
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   git clone https://github.com/researchpulse/researchpulse.git
   cd researchpulse

2. Create Virtual Environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # or
   venv\Scripts\activate  # Windows

3. Install Dependencies
^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pip install -r requirements.txt
   pip install -e ".[embedding]"  # Optional: vector embeddings
   pip install -e ".[dev]"        # Optional: development tooling

4. Configure Environment
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   # Copy example configuration
   cp .env.example .env

   # Edit configuration
   vim .env

Required configuration:

.. code-block:: bash

   # Database
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=research_pulse
   DB_USER=your_user
   DB_PASSWORD=your_password

   # Superuser (first-time setup)
   SUPERUSER_USERNAME=admin
   SUPERUSER_EMAIL=admin@example.com
   SUPERUSER_PASSWORD=secure_password

5. Initialize Database
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   # Create database
   mysql -u root -p -e "CREATE DATABASE research_pulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

   # Initialize tables
   mysql -u root -p research_pulse < sql/init.sql

6. Start the Application
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   python main.py

The service will start at ``http://localhost:8000``.

7. Optional Services
^^^^^^^^^^^^^^^^^^^^

Start Milvus (for vector embeddings):

.. code-block:: bash

   docker-compose -f docker-compose.milvus.yml up -d

Start Ollama (for local AI inference):

.. code-block:: bash

   ollama serve
   ollama pull qwen3:32b

Access Points
-------------

+------------------+-----------------------------------------+
| Service          | URL                                     |
+==================+=========================================+
| Main App         | http://localhost:8000/                  |
+------------------+-----------------------------------------+
| ResearchPulse UI | http://localhost:8000/researchpulse/    |
+------------------+-----------------------------------------+
| Admin Panel      | http://localhost:8000/researchpulse/admin |
+------------------+-----------------------------------------+
| API Docs         | http://localhost:8000/docs              |
+------------------+-----------------------------------------+

Troubleshooting
---------------

Database Connection Errors
^^^^^^^^^^^^^^^^^^^^^^^^^^

Check your ``.env`` configuration:

.. code-block:: bash

   mysql -h $DB_HOST -P $DB_PORT -u $DB_USER -p$DB_PASSWORD -e "SHOW DATABASES;"

Import Errors
^^^^^^^^^^^^^

Ensure you're using the correct Python environment:

.. code-block:: bash

   python --version
   pip list | grep -i researchpulse

Port Already in Use
^^^^^^^^^^^^^^^^^^^

Change the port in your ``.env``:

.. code-block:: bash

   APP_PORT=8001
