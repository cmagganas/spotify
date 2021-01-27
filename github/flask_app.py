import os
from flask import Flask, session, request, redirect, render_template, url_for
from flask_session import Session
from CreatePlaylist import CreatePlaylist
from SpotifyMySQLmodule import DataFrame_to_sql
import GetUserTop
import uuid
from werkzeug.middleware.profiler import ProfilerMiddleware

# ENVIRONMENTAL VARIABLES
os.environ['SPOTIPY_CLIENT_ID'] = ''
os.environ['SPOTIPY_CLIENT_SECRET'] = ''
os.environ['SPOTIPY_REDIRECT_URI'] = 'https://www.christos.app/spotify/'

# Flask
app = Flask(__name__)

# Spotipy App
app.config['SECRET_KEY'] = os.urandom(64)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = './.flask_session/'

# werkzeug profiler
app.config['PROFILE'] = True
app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions = [100], sort_by=('cumtime', 'nfl'))
Session(app)

caches_folder = './.spotify_caches/'
if not os.path.exists(caches_folder):
    os.makedirs(caches_folder)

def session_cache_path():
    return caches_folder + session.get('uuid')

######################################################
# HOME / BIO

@app.route('/')
def home():
    return render_template('christos_index.html')


######################################################
# SPOTIFY APP

@app.route('/spotify/', methods=['GET', 'POST'])
def spotify():

    # Step 1. Visitor is unknown, give random ID
    if not session.get('uuid'):
        session['uuid'] = str(uuid.uuid4())
        session['signed_in'] = False
        session['playlist_type'] = None

    # Step 2. POST request via form
    # set tuning params
    playlist_params = {'seed_genres':'dance','num_tracks':69,'popularity':'popular','mood':'any','release_date':'any'} # example

    if request.method == 'POST':
        session['playlist_type'] = request.form.get('playlist_type')
        genre = request.form.get('genre')
        num_tracks = request.form.get('num_tracks')
        popularity = request.form.get('popularity')
        mood = request.form.get('mood')
        release_date = request.form.get('release_date')
        playlist_params.update({'seed_genres':genre,'num_tracks':num_tracks,'popularity':popularity,'mood':mood,'release_date':release_date})

    # Step 3. if code then SIGNED IN
    if request.args.get('code'):

        # SIGNED IN
        session['signed_in'] = True

        # Grab code and state from redirect URL
        code = request.args.get('code')
        if request.args.get('state'):
            session['playlist_type'] = request.args.get('state')

        # use session_cache_path and code to get user top
        session['display_name'], session['user_id'], user_top_tracks_df = GetUserTop.auth_n_code(session_cache_path(), code)
        # add/update top tracks to SQL DB
        DataFrame_to_sql(user_top_tracks_df, session['user_id'])

        return redirect(url_for('spotify'))

    # Step 3b. if error then remove cache
    if request.args.get('error'):
        return redirect(url_for('sign_out'))

    # Step 4. Determine whether to create playlist
    if session['playlist_type'] != None:
        # I
        if session['playlist_type'] == 'I':
            playlist_link = CreatePlaylist(None, **playlist_params)
        # II or III
        if session['playlist_type'] in ['II','III']:
            # make sure signed in
            if session['signed_in'] == False:
                return redirect('/spotify/sign_in')
            user_ids = [session['user_id']]
            # III
            if session['playlist_type'] == 'III':
                user_ids.append('1291320337')
            playlist_link = CreatePlaylist(user_ids, **playlist_params)
        # reset once playlist is created
        session['playlist_type'] = None
        session['playlist_link'] = playlist_link
        session['playlist_embed_link'] = playlist_link.replace(".com/",".com/embed/")

    url_arg_dict = {}
    for arg in session.keys():
        url_arg_dict[arg] = session[arg]
    # Display app whether signed in or out
    return render_template('christos_spotify.html', **url_arg_dict)

@app.route('/spotify/sign_in')
def sign_in():
    client_id = '' # insert app client id
    auth_url = f"https://accounts.spotify.com/en/authorize?client_id={client_id}&response_type=code&redirect_uri=https%3A%2F%2Fwww.christos.app%2Fspotify%2F&scope=user-top-read&show_dialog=True"
    return redirect(auth_url)

@app.route('/spotify/sign_out')
def sign_out():
    try:
        session.clear()
        # remove all files from './.flask_session/'
        os.system('rm -rf ./.flask_session/*')
        # remove all files from './.spotify_caches/' except .cache-{spotify username}
        d='/home/cmagganas/.spotify_caches/'
        spotify_username = '' # insert username where developer app was created
        filesToRemove = [os.path.join(d,f) for f in os.listdir(d) if f != '.cache-{spotify_username}']
        for f in filesToRemove:
            os.remove(f)
    except OSError as e:
        print ("Error: %s - %s." % (e.filename, e.strerror))
    return redirect('/spotify/')

@app.errorhandler(Exception)
def handle_error(e):
    print(e)
    return redirect('/spotify/sign_out')

# SPOTIFY STOP
######################################################