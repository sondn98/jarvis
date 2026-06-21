from api_server.app import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=app.state.config.host, port=app.state.config.port)
