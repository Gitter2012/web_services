Configuration Guide
===================

Configuration Sources
---------------------

ResearchPulse uses a multi-level configuration system:

1. ``.env`` - Environment variables (secrets, passwords)
2. ``config/defaults.yaml`` - Non-sensitive defaults
3. ``system_config`` database table - Runtime configuration overrides

Environment Variables (.env)
-----------------------------

Database Configuration
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=research_pulse
   DB_USER=research_user
   DB_PASSWORD=your_password

Application Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   APP_NAME=ResearchPulse
   DEBUG=false
   DATA_DIR=./data
   URL_PREFIX=/researchpulse

JWT Configuration
^^^^^^^^^^^^^^^^^

.. code-block:: bash

   JWT_SECRET_KEY=your-secret-key  # Auto-generated if empty

Redis Configuration (Optional)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_PASSWORD=
   REDIS_DB=0

Email Configuration
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   EMAIL_ENABLED=false
   EMAIL_FROM=your-email@gmail.com
   EMAIL_BACKEND=smtp

   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   SMTP_TLS=true

   SENDGRID_API_KEY=
   MAILGUN_API_KEY=
   MAILGUN_DOMAIN=
   BREVO_API_KEY=

YAML Configuration (config/defaults.yaml)
-----------------------------------------

Application Settings
^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   app:
     name: ResearchPulse
     debug: false
     data_dir: ./data
     url_prefix: /researchpulse

Database Pool Settings
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   database:
     pool_size: 10
     max_overflow: 20
     pool_recycle: 3600
     echo: false

Crawler Settings
^^^^^^^^^^^^^^^^

.. code-block:: yaml

   crawler:
     arxiv:
       categories: cs.LG,cs.CV,cs.IR,cs.CL,cs.DC
       max_results: 50
       delay_base: 3.0
       delay_jitter: 1.5
     rss:
       timeout: 30
       max_concurrent: 5

AI Processor Settings
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   ai_processor:
     enabled: false
     provider: "ollama"  # ollama, openai, claude

     ollama:
       base_url: "http://localhost:11434"
       model: "qwen3:32b"
       timeout: 120
       api_key: ""  # Optional, for authenticated remote Ollama

     openai:
       model: "gpt-4o"
       model_light: "gpt-4o-mini"
       base_url: "https://api.openai.com/v1"  # Custom proxy or compatible API

     claude:
       model: "claude-sonnet-4-20250514"

     cache:
       enabled: true
       ttl: 86400

     max_content_length: 1500

Embedding Settings
^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   embedding:
     enabled: false
     provider: "sentence-transformers"
     model: "all-MiniLM-L6-v2"
     dimension: 384

     milvus:
       host: "localhost"
       port: 19530
       collection_name: "article_embeddings"

Event Clustering Settings
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   event:
     enabled: false
     clustering:
       rule_weight: 0.4
       semantic_weight: 0.6
       min_similarity: 0.7

Feature Toggles
---------------

All features can be toggled at runtime:

+------------------------+-----------------------------+---------+
| Feature                | Key                         | Default |
+========================+=============================+=========+
| Crawler                | ``feature.crawler``         | true    |
+------------------------+-----------------------------+---------+
| Backup                 | ``feature.backup``          | true    |
+------------------------+-----------------------------+---------+
| Cleanup                | ``feature.cleanup``         | true    |
+------------------------+-----------------------------+---------+
| AI Processor           | ``feature.ai_processor``    | false   |
+------------------------+-----------------------------+---------+
| Embedding              | ``feature.embedding``       | false   |
+------------------------+-----------------------------+---------+
| Event Clustering       | ``feature.event_clustering``| false   |
+------------------------+-----------------------------+---------+
| Topic Radar            | ``feature.topic_radar``     | false   |
+------------------------+-----------------------------+---------+
| Action Items           | ``feature.action_items``    | false   |
+------------------------+-----------------------------+---------+
| Report Generation      | ``feature.report_generation``| false  |
+------------------------+-----------------------------+---------+
| Email Notification     | ``feature.email_notification``| false |
+------------------------+-----------------------------+---------+

Toggle via API:

.. code-block:: bash

   curl -X PUT http://localhost:8000/api/v1/admin/features/feature.ai_processor \
     -H "Content-Type: application/json" \
     -d '{"enabled": true}'

Scheduler Configuration
-----------------------

+----------------+----------------------+------------------------------------+
| Task           | Default Schedule     | Config Key                         |
+================+======================+====================================+
| Crawl          | Every 6 hours        | ``scheduler.crawl_interval_hours`` |
+----------------+----------------------+------------------------------------+
| Cleanup        | 3 AM daily           | ``scheduler.cleanup_hour``         |
+----------------+----------------------+------------------------------------+
| Backup         | 4 AM daily           | ``scheduler.backup_hour``          |
+----------------+----------------------+------------------------------------+
| AI Process     | Every 1 hour         | ``scheduler.ai_process_interval_hours`` |
+----------------+----------------------+------------------------------------+
| Embedding      | Every 2 hours        | ``scheduler.embedding_interval_hours`` |
+----------------+----------------------+------------------------------------+
| Event Cluster  | 2 AM daily           | ``scheduler.event_cluster_hour``   |
+----------------+----------------------+------------------------------------+
| Topic Discovery| 1 AM Mondays         | ``scheduler.topic_discovery_hour``, ``scheduler.topic_discovery_day`` |
+----------------+----------------------+------------------------------------+
