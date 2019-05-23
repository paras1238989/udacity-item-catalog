from functools import wraps
from flask import Flask, render_template, request, redirect, jsonify, url_for, flash  # noqa
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, CatalogItem, Category, User
from flask import session as login_session
import random
import string
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests


app = Flask(__name__)


CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Item Catalog Application"


# Connect to Database and create database session
engine = create_engine('sqlite:///itemcatalog.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in login_session:
            return redirect(url_for('showLogin'))
        return f(*args, **kwargs)
    return decorated_function


# --------------------------------------
# JSON APIs to show Catalog information
# --------------------------------------
@app.route('/api/v1/catalog.json')
def showCatalogJSON():
    """Returns JSON of all items in catalog"""
    items = session.query(CatalogItem).order_by(CatalogItem.id.desc())
    return jsonify(CatalogItems=[i.serialize for i in items])


@app.route(
    '/api/v1/categories/<int:category_id>/item/<int:catalog_item_id>/JSON')
def catalogItemJSON(category_id, catalog_item_id):
    """Returns JSON of selected item in catalog"""
    Catalog_Item = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    return jsonify(Catalog_Item=Catalog_Item.serialize)


@app.route('/api/v1/categories/JSON')
def categoriesJSON():
    """Returns JSON of all categories in catalog"""
    categories = session.query(Category).all()
    return jsonify(Categories=[r.serialize for r in categories])


# --------------------------------------
# CRUD for categories
# --------------------------------------
# READ - home page, show latest items and categories
@app.route('/')
@app.route('/categories/')
def showCatalog():
    """Returns catalog page with all categories and recently added items"""
    categories = session.query(Category).all()
    items = session.query(CatalogItem).order_by(CatalogItem.id.desc())
    quantity = items.count()
    if 'username' not in login_session:
        return render_template(
            'public_catalog.html',
            categories=categories, items=items, quantity=quantity)
    else:
        return render_template(
            'catalog.html',
            categories=categories, items=items, quantity=quantity)


# CREATE - New category
@app.route('/categories/new', methods=['GET', 'POST'])
@login_required
def newCategory():
    """Allows user to create new category"""
    if request.method == 'POST':
        if 'user_id' not in login_session and 'email' in login_session:
            login_session['user_id'] = getUserID(login_session['email'])
        newCategory = Category(
            name=request.form['name'],
            user_id=login_session['user_id'])
        session.add(newCategory)
        session.commit()
        flash("New category created!", 'success')
        return redirect(url_for('showCatalog'))
    else:
        return render_template('new_category.html')


# EDIT a category
@app.route('/categories/<int:category_id>/edit/', methods=['GET', 'POST'])
@login_required
def editCategory(category_id):
    """Allows user to edit an existing category"""
    editedCategory = session.query(
        Category).filter_by(id=category_id).one()
    if editedCategory.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        if request.form['name']:
            editedCategory.name = request.form['name']
            flash(
                'Category Successfully Edited %s' % editedCategory.name,
                'success')
            return redirect(url_for('showCatalog'))
    else:
        return render_template(
            'edit_category.html', category=editedCategory)


# DELETE a category
@app.route('/categories/<int:category_id>/delete/', methods=['GET', 'POST'])
@login_required
def deleteCategory(category_id):
    """Allows user to delete an existing category"""
    categoryToDelete = session.query(
        Category).filter_by(id=category_id).one()
    if categoryToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        session.delete(categoryToDelete)
        flash('%s Successfully Deleted' % categoryToDelete.name, 'success')
        session.commit()
        return redirect(
            url_for('showCatalog', category_id=category_id))
    else:
        return render_template(
            'delete_category.html', category=categoryToDelete)


# --------------------------------------
# CRUD for category items
# --------------------------------------
# READ - show category items
@app.route('/categories/<int:category_id>/')
@app.route('/categories/<int:category_id>/items/')
def showCategoryItems(category_id):
    """returns items in category"""
    category = session.query(Category).filter_by(id=category_id).one()
    categories = session.query(Category).all()
    creator = getUserInfo(category.user_id)
    items = session.query(
        CatalogItem).filter_by(
            category_id=category_id).order_by(CatalogItem.id.desc())
    quantity = items.count()
    return render_template(
        'catalog_menu.html',
        categories=categories,
        category=category,
        items=items,
        quantity=quantity,
        creator=creator)


# READ ITEM - selecting specific item show specific information about that item
@app.route('/categories/<int:category_id>/item/<int:catalog_item_id>/')
def showCatalogItem(category_id, catalog_item_id):
    """returns category item"""
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    creator = getUserInfo(category.user_id)
    return render_template(
        'catalog_menu_item.html',
        category=category, item=item, creator=creator)


# CREATE ITEM
@app.route('/categories/item/new', methods=['GET', 'POST'])
@login_required
def newCatalogItem():
    """return "This page will be for making a new catalog item" """
    categories = session.query(Category).all()
    if request.method == 'POST':
        addNewItem = CatalogItem(
            name=request.form['name'],
            description=request.form['description'],
            price=request.form['price'],
            category_id=request.form['category'],
            user_id=login_session['user_id'])
        session.add(addNewItem)
        session.commit()
        flash("New catalog item created!", 'success')
        return redirect(url_for('showCatalog'))
    else:
        return render_template('new_catalog_item.html', categories=categories)


# UPDATE ITEM
@app.route(
    '/categories/<int:category_id>/item/<int:catalog_item_id>/edit',
    methods=['GET', 'POST'])
@login_required
def editCatalogItem(category_id, catalog_item_id):
    """return "This page will be for making a updating catalog item" """
    editedItem = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    if editedItem.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['category']:
            print editedItem.category
            editedItem.category.id = request.form['category']
        session.add(editedItem)
        session.commit()
        flash("Catalog item updated!", 'success')
        return redirect(url_for('showCatalog'))
    else:
        categories = session.query(Category).all()
        return render_template(
            'edit_catalog_item.html',
            categories=categories,
            item=editedItem)


# DELETE ITEM
@app.route(
    '/categories/<int:category_id>/item/<int:catalog_item_id>/delete',
    methods=['GET', 'POST'])
@login_required
def deleteCatalogItem(category_id, catalog_item_id):
    """return "This page will be for deleting a catalog item" """
    itemToDelete = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    if itemToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Catalog Item Successfully Deleted', 'success')
        return redirect(url_for('showCatalog'))
    else:
        return render_template(
            'delete_catalog_item.html', item=itemToDelete)


# --------------------------------------
# Login Handling
# --------------------------------------

# Login route, create anit-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(
        random.choice(
            string.ascii_uppercase + string.digits) for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


# CONNECT - Google login get token
@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data
    token = request.data
    # Request an access token from google API
    idinfo = id_token.verify_oauth2_token(
                 code,
                 google_requests.Request(),
                 CLIENT_ID)
    # Trigger the Google url and receive the token
    url = ('https://oauth2.googleapis.com/tokeninfo?id_token=%s' % token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])

    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user
    user_google_id = idinfo['sub']
    if result['sub'] != user_google_id:
        response = make_response(
            json.dumps("Token's user id does not match given user id"),
            401
        )
        response.headers['Content-Type'] = 'application/json'
        return response

    if result['aud'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client id does not match app's"),
            401
        )
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check if user already logged in
    stored_access_token = login_session.get('access_token')
    stored_user_google_id = login_session.get('user_google_id')
    if (stored_access_token is not None and
            user_google_id == stored_user_google_id):

        response = make_response(
            json.dumps('Current user is already connected'), 200
        )
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = idinfo
    login_session['gplus_id'] = user_google_id

    # Get user info
    login_session['provider'] = 'google'
    login_session['username'] = idinfo['name']
    login_session['picture'] = idinfo['picture']
    login_session['email'] = idinfo['email']

    # see if user exists, if not create new user
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '  # noqa
    flash("you are now logged in as %s" % login_session['username'], 'success')
    return output


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
    # only disconnect a connected user
    credentials = login_session.get('credentials')
    if credentials is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-type'] = 'application/json'
        return response
    # execute HTTP GET request to revoke current token
    access_token = credentials.access_token
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % login_session['access_token']  # noqa
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # reset the user's session
        del login_session['credentials']
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    else:
        # token given is invalid
        response = make_response(
            json.dumps('Failed to revoke token for given user.'), 400)
        response.headers['Content-Type'] = 'application/json'
        return response


# User helper functions
def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except Exception as e:
        return None


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def createUser(login_session):
    newUser = User(
        name=login_session['username'],
        email=login_session['email'],
        picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


# Disconnect based on provider
@app.route('/disconnect')
def disconnect():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            if 'gplus_id' in login_session:
                del login_session['gplus_id']
            if 'credentials' in login_session:
                del login_session['credentials']
        if 'username' in login_session:
            del login_session['username']
        if 'email' in login_session:
            del login_session['email']
        if 'picture' in login_session:
            del login_session['picture']
        if 'user_id' in login_session:
            del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.", 'success')
        return redirect(url_for('showCatalog'))
    else:
        flash("You were not logged in", 'danger')
        return redirect(url_for('showCatalog'))


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=5000, threaded=False)
