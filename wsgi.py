from wms import create_app
from wms.seed import seed
app = create_app(); seed(app)
if __name__ == '__main__': app.run(debug=False)
