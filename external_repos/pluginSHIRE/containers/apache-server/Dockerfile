# Use the official Apache HTTP Server image
FROM httpd:latest

# UID and GID default to 1000 if not given
ARG UID=1000
ARG GID=1000

# Install basic tools for debugging
RUN apt-get update && \
    apt-get install -y nano curl

# Create user with UID and GID of user with access to local volume mount
RUN groupadd -g ${GID} www-data || groupmod -g ${GID} www-data && \
    useradd -u ${UID} -g ${GID} -d /usr/local/apache2/htdocs -s /bin/bash -M www-data || \
    usermod -u ${UID} -g ${GID} www-data

# Create necessary directories and files for WebDAV
RUN mkdir -p /usr/local/apache2/var /usr/local/apache2/htdocs/data && \
touch /usr/local/apache2/var/DavLock

# overwrite httpd config file
COPY ./httpd-config.conf /usr/local/apache2/conf/httpd.conf

# Set permissions and ownership for apache and htdocs folder
RUN chown -R www-data:www-data /usr/local/apache2 && \
chmod -R 755 /usr/local/apache2/htdocs

# Expose the apache HTTP port
EXPOSE 8081

# Run Apache HTTP Server in the foreground
USER www-data
CMD ["httpd-foreground"]
