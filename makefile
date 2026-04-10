start:
	@fastapi dev app/main.py & arq app.worker.WorkerSettings & wait

worker:
	@arq app.worker.WorkerSettings


migrate-create:
ifndef message
	@read -p "Migration message: " msg && alembic revision --autogenerate -m "$$msg"
else
	@alembic revision --autogenerate -m "$(message)"
endif



migrate:
	@alembic upgrade head
