chmod +x generate-certs.sh

# Pour dev local

./generate-certs.sh localhost local

# Pour une VM de production

sudo ./generate-certs.sh mon-domaine.fr prod
