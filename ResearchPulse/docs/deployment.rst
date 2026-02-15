Deployment Guide
================

Production Deployment
---------------------

Server Requirements
^^^^^^^^^^^^^^^^^^^

- OS: Ubuntu 20.04+ / CentOS 8+
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB SSD
- Python: 3.10+

Install Dependencies
^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3.10 python3-pip python3-venv git mysql-server
   git clone https://github.com/researchpulse/researchpulse.git
   cd researchpulse

Configure MySQL
^^^^^^^^^^^^^^^

.. code-block:: bash

   sudo mysql_secure_installation

   sudo mysql -u root -p <<EOF
   CREATE DATABASE research_pulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'research_user'@'localhost' IDENTIFIED BY 'your_secure_password';
   GRANT ALL PRIVILEGES ON research_pulse.* TO 'research_user'@'localhost';
   FLUSH PRIVILEGES;
   EOF

   mysql -u research_user -p research_pulse < sql/init.sql

Configure Application
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   cp .env.example .env
   vim .env

   # Example values
   DEBUG=false
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=research_pulse
   DB_USER=research_user
   DB_PASSWORD=your_secure_password

Install Application
^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python main.py

Systemd Service
^^^^^^^^^^^^^^^

Create ``/etc/systemd/system/researchpulse.service``:

.. code-block:: ini

   [Unit]
   Description=ResearchPulse Service
   After=network.target mysql.service

   [Service]
   Type=simple
   User=www-data
   Group=www-data
   WorkingDirectory=/opt/researchpulse
   Environment="PATH=/opt/researchpulse/venv/bin"
   ExecStart=/opt/researchpulse/venv/bin/python main.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target

Enable and start:

.. code-block:: bash

   sudo systemctl daemon-reload
   sudo systemctl enable researchpulse
   sudo systemctl start researchpulse

Nginx Reverse Proxy
^^^^^^^^^^^^^^^^^^^

Create ``/etc/nginx/sites-available/researchpulse``:

.. code-block:: nginx

   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }

Enable and reload:

.. code-block:: bash

   sudo ln -s /etc/nginx/sites-available/researchpulse /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx

Docker Deployment
-----------------

Using Docker Compose
^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   version: '3.8'

   services:
     app:
       build: .
       ports:
         - "8000:8000"
       environment:
         - DB_HOST=db
         - DB_PORT=3306
         - DB_NAME=research_pulse
         - DB_USER=research_user
         - DB_PASSWORD=your_password
       depends_on:
         - db
       volumes:
         - ./data:/app/data

     db:
       image: mysql:8.0
       environment:
         - MYSQL_ROOT_PASSWORD=root_password
         - MYSQL_DATABASE=research_pulse
         - MYSQL_USER=research_user
         - MYSQL_PASSWORD=your_password
       volumes:
         - mysql_data:/var/lib/mysql
       ports:
         - "3306:3306"

   volumes:
     mysql_data:

Run:

.. code-block:: bash

   docker-compose up -d

SSL/HTTPS
---------

Using Certbot
^^^^^^^^^^^^^

.. code-block:: bash

   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   sudo certbot renew --dry-run

Monitoring
----------

Health Check
^^^^^^^^^^^^

.. code-block:: bash

   curl http://localhost:8000/health

Logs
^^^^

.. code-block:: bash

   sudo journalctl -u researchpulse -f

Backup Strategy
---------------

Database Backup
^^^^^^^^^^^^^^^

.. code-block:: bash

   mysqldump -u research_user -p research_pulse > /backup/research_pulse_$(date +%Y%m%d).sql

Application Backup
^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   tar -czf researchpulse_backup_$(date +%Y%m%d).tar.gz \
     .env \
     data/ \
     config/
