## Clone module
```shell
git clone git@github.com:TASCB/openimis-be-grievance_social_protection_py.git
git checkout tz-changes
```

## Install the module in editable mode to be able to test it locally.
```shell
pip install -e openimis-be-grievance_social_protection_py
```

## Run migration
```shell
python manage.py makemigrations grievance_social_protection
python manage.py migrate
```

## Seed
```shell
python manage.py seed_grievances
```