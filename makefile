start:
	@fastapi dev main.py


migrate-create:
ifndef message
	@read -p "Migration message: " msg && alembic revision --autogenerate -m "$$msg"
else
	@alembic revision --autogenerate -m "$(message)"
endif



migrate:
	@alembic upgrade head
