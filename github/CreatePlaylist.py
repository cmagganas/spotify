import numpy as np                                      # data formatting
import pandas as pd                                     # data formatting
from sklearn.preprocessing import StandardScaler        # scale feature distribution
from sklearn.cluster import AffinityPropagation         # clustering model
import datetime                                         # get current time
from fastdist import fastdist                           # score recommendations
import spotipy                                          # spotipy
import json                                             # json
import time                                             # time
# query MySQL DB given user id(s)
from SpotifyMySQLmodule import ReadMySQL

def is_token_expired(token_info):
    now = int(time.time())
    return token_info['expires_at'] - now < 60

CLIENT_ID = ''
CLIENT_SECRET = ''
username = ''
SCOPE = "playlist-modify-private playlist-modify-public playlist-read-collaborative playlist-read-private user-library-read user-top-read"
REDIRECT_URI = "https://www.christos.app/spotify/"
# where token info is saved
cache_path = "./.spotify_caches/.cache-{}"

auth_manager = spotipy.oauth2.SpotifyOAuth(
    username=username, scope=SCOPE, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI, cache_path=cache_path)

# SpotifyAPI Class
class SpotifyAPI(object):

    def __init__(self, spotify, *args, **kwargs):
        #super().__init__(*args, **kwargs)
        self.spotify = spotify
        self.sql2df = kwargs.get('sql2df',None)
        self.userIDs = kwargs.get('userIDs',None)

    def current_user(self):
        return self.spotify.current_user()

    def search(self, query, **params):
        return self.spotify.search(query, limit=50, offset=0, type='artist', market=None)

    def audio_features(self, track_ids=[]):
        resp_list = []
        i=0
        while len(track_ids)/100 > i:
            resp = self.spotify.audio_features(tracks=track_ids[100*i:100*i+100])
            resp_list.append(resp)
            i+=1
        resp_list = [x for y in resp_list for x in y]
        return pd.DataFrame(resp_list)

    def artist_related_artists(self, artist_id):
        return self.spotify.artist_related_artists(artist_id)

    def artist_top_tracks(self, artist_id, country='US'):
        return self.spotify.artist_top_tracks(artist_id, country=country)

    def current_user_top_artists(self, limit=50, offset=0, time_range='medium_term'):
        return self.spotify.current_user_top_artists(limit=limit, offset=offset, time_range=time_range)

    def current_user_top_tracks(self, limit=50, offset=0, time_range='medium_term'):
        return self.spotify.current_user_top_tracks(limit=limit, offset=offset, time_range=time_range)

    def current_user_playlists(self, limit=50, offset=0):
        return self.spotify.current_user_playlists(limit=limit, offset=offset)

    def get_playlists_tracks(self, playlist_id):
        resp_list = []
        i=0
        resp=True
        while resp:
            resp = self.spotify.playlist_tracks(playlist_id, limit=100, offset=100*i)['items']
            resp_list.append(resp)
            i+=1
        resp_list.pop()
        resp_list = [x for y in resp_list for x in y]
        return resp_list # list of dicts

    def recommendations(self, seed_artists=None, seed_genres=None, seed_tracks=None, limit=100, country='US', **kwargs):
        return self.spotify.recommendations(seed_artists, seed_genres, seed_tracks, limit, country, **kwargs)

    def get_tracks(self, tracks):
        tracks_lod = [item for sublist in [self.spotify.tracks(tracks[i:i+50])['tracks'] for i in range(0, len(tracks), 50)] for item in sublist] if len(tracks)>50 else self.spotify.tracks(tracks)['tracks']
        return tracks_lod

    def user_playlist_create(self, name="DiscoverQuickly", public=True, collaborative=False):
        user = self.current_user()['id']
        description = f"playlist generated on {datetime.datetime.now():%c}"
        response_json = self.spotify.user_playlist_create(user, name, public, collaborative, description)
        return response_json["id"] # playlist id

    def add_song_to_playlist(self, tracks):
        # create a new playlist
        playlist_id = self.user_playlist_create()
        link = 'https://open.spotify.com/playlist/{}'.format(playlist_id)

        # add all songs into new playlist
        user = self.current_user()['id']
        self.spotify.user_playlist_add_tracks(user, playlist_id, tracks)

        return link

    # CLUSTERING PORTION

    def standard_scale_audio_features_df(self, df):
        cols=['danceability','energy','loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo']
        X = df[cols]
        X_std = StandardScaler().fit_transform(X)
        X_std = pd.DataFrame(X_std,columns=X.columns)
        df[cols] = X_std
        return df

    def add_audio_features(self, df):
        audio_features = self.audio_features(list(df['id']))
        audio_features = pd.DataFrame(audio_features, columns=['id','danceability','energy','loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo'])
        audio_features.id = audio_features.id.astype(str)
        df.id = df.id.astype(str)
        df_with_added_audio_features = df.merge(audio_features, left_on='id', right_on='id')
        return df_with_added_audio_features

    def get_user_top_tracks(self, time_range='medium_term', **kwargs):
        # get user's top tracks from sql table if exists, otherwise call spotipy api
        if self.sql2df is not None:
            user_top_df = self.sql2df[self.sql2df.user_id.isin(self.userIDs)]
        else:
            user_top_json = self.spotify.current_user_top_tracks(limit=50, offset=0, time_range=time_range)
            user_top_df = pd.json_normalize(user_top_json['items'])
        user_top_df = self.add_audio_features(user_top_df)#.set_index('index')
        return user_top_df

    def cluster_df(self, df, preference=np.random.randint(-15, -5)):
        cols=['danceability','energy','loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo']
        X = df[cols]
        X_std = StandardScaler().fit_transform(X)
        X_std = pd.DataFrame(X_std,columns=X.columns)
        # Affinity Prop
        af = AffinityPropagation(preference=preference,max_iter=1000,verbose=True,damping=0.9,random_state=None).fit(X_std) # best preference range -> [-15,-5]
        cluster_centers_indices = af.cluster_centers_indices_
        labels = af.labels_
        df['cluster'] = labels
        df['dist'] = X_std.apply(lambda row: fastdist.euclidean(np.array(row),np.array(X_std.iloc[cluster_centers_indices[labels[row.name]]])),axis=1).round(2)
        return df.sort_values(['cluster','dist'])

    def cluster_combined_top(self):
        # clusters top tracks from all users
        combined_top_df = self.get_user_top_tracks()
        clustered_df = self.cluster_df(combined_top_df)
        return clustered_df

    def set_popularity(self, popularity_tier='none'):
        "Popularity parameter should be set by user"
        pop_dict = {'none':{},
                    'obscure':{'max_popularity':25},
                    'esoteric':{'min_popularity':10,'max_popularity':75},
                    'popular':{'min_popularity':50}}
        return pop_dict[popularity_tier]

    def set_query_parameters(self, df, target_cols=[], **params):
        df_desc = df.describe()
        df_desc['loudness'] = df.loudness.apply(lambda x: np.e**x).describe().apply(lambda x: np.log(x))
        minmax_cols = ['danceability','energy','loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo']
        query_parameter_dict = dict()
        for para in minmax_cols:
            query_parameter_dict[f'min_{para}'] = df_desc[para]['min']
            query_parameter_dict[f'max_{para}'] = df_desc[para]['max']
            if para in target_cols:
                query_parameter_dict[f'target_{para}'] = df_desc[para]['50%'] # '50%' or 'mean' TBD
        for key, value in params.items():
            query_parameter_dict[f'{key}'] = value
        return query_parameter_dict

    def combined_top_recs(self, **kwargs):
        # gets recs for clustered tracks
        df = self.cluster_combined_top()
        recs = []
        for c in df.cluster.unique():
            df_c = df[df.cluster==c]
            # pass in playlist preferences for tuning
            """Need to decide what parameters to tune ... if any min_*, max_* or target_* should be set"""
            params = self.set_query_parameters(df_c,**self.set_popularity())
            params.update(kwargs)
            cluster_recs = self.recommendations(seed_tracks=df_c.id.head().tolist(), limit=100, **params)['tracks']
            if len(cluster_recs)>0:
                rec_list = pd.json_normalize(cluster_recs)['id'].tolist()
                cluster_recs_tracks = self.get_tracks(rec_list) # -> throw that error back <-
                cluster_recs_df = pd.json_normalize(cluster_recs_tracks,sep='_').rename(columns={"album_release_date":"release_date"})
                cluster_recs_df['cluster'] = c
                recs.append(cluster_recs_df)
        concat_df = pd.concat(recs) #[['artists','name','id','popularity','cluster']]
        #concat_df.artists = concat_df.artists.apply(lambda x: ", ".join([x[i]['name'] for i in range(0,len(x))]))
        return concat_df

    def user_features_clustered(self, **kwargs):
        # groups user top by cluster, takes mean of audio-features
        user_top = self.get_user_top_tracks(**kwargs)
        X = self.cluster_df(user_top)
        X.loudness = X.loudness.apply(lambda x: np.e**x)
        X = X.groupby('cluster')[['danceability','energy','loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo']].mean()
        X.loudness = X.loudness.apply(lambda x: np.log(x))
        X_std = pd.DataFrame(StandardScaler().fit_transform(X), columns=X.columns)
        return X_std

    def score_recs(self, **kwargs):
        # remove release_date range from tuning params dict
        release_date_period = kwargs['release_date']
        del kwargs['release_date']
        # scores recs for clustered tracks"
        all_recs = self.combined_top_recs(**kwargs)[['artists','name','id','popularity','release_date','cluster']] # added 'album_release_date'
        all_recs.artists = all_recs.artists.apply(lambda x: ", ".join([x[i]['name'] for i in range(0,len(x))]))
        score_df = self.standard_scale_audio_features_df(self.add_audio_features(all_recs))
        users = []
        # add all clustered user-feature dfs here
        if self.userIDs is not None:
            users.extend([self.user_features_clustered(user_id=user_id) for user_id in self.userIDs])
        else:
            users.append(self.user_features_clustered())
        cols = ['danceability','energy','loudness','speechiness','acousticness','instrumentalness','liveness','valence','tempo']
        score_list = []
        for user in users:
            score_list.append(np.amin(fastdist.matrix_to_matrix_distance(score_df[cols].to_numpy(), user.to_numpy(), fastdist.euclidean, "euclidean"), axis=1).round(2))
        score_df['score']=pd.DataFrame(score_list).max()
        score_df = score_df.drop_duplicates(subset=score_df.columns.difference(['cluster'])).sort_values('score')
        # define filter by release date function
        def filter_by_release_date(df,_period):
            df.release_date = pd.to_datetime(df.release_date)
            now = datetime.datetime.now()
            last_month = now.replace(month = now.month - 1 if now.month > 1 else 12)
            last_year = now.replace(year = now.year - 1)
            if _period == 'last_year':
                return df[df.release_date > last_year]
            if _period == 'last_month':
                return df[df.release_date > last_month]
            return df
        # filter by release date if at all
        score_df = filter_by_release_date(score_df,release_date_period)
        return score_df

    def make_playlist(self, **kwargs):
        # remove track limit from tuning params dict
        limit = int(kwargs["num_tracks"]) if kwargs["num_tracks"] else 20
        kwargs.pop("num_tracks", None)
        songs_to_add = [f"spotify:track:{x}" for x in self.score_recs(**kwargs).id.head(limit)]
        link = self.add_song_to_playlist(songs_to_add)
        return link

# define function to call
def CreatePlaylist(userIDs=None, **kwargs):

    # refresh token
    with open(cache_path,'r+') as f:
        s = f.read()
        s = s.replace('\'','\"')
        cached_token_info = json.loads(s)
        if is_token_expired(cached_token_info):
            # use refresh token to get access token
            cached_token_info = auth_manager.refresh_access_token(cached_token_info['refresh_token'])
            f.seek(0)
            json.dump(cached_token_info, f)
            f.truncate()

    # set up spotify api
    spotify = spotipy.Spotify(auth_manager=auth_manager)

    # format tuning params
    playlist_tuner = {key: [value] if key in ['seed_artists','seed_genres','seed_tracks'] else value for key,value in kwargs.items()}
    # set pop params
    pop_dict = {'any':{},
            'obscure':{'max_popularity':25},
            'esoteric':{'min_popularity':10,'max_popularity':75},
            'popular':{'min_popularity':50}}
    popularity = pop_dict[playlist_tuner['popularity']]
    del playlist_tuner['popularity']
    playlist_tuner.update(popularity)
    # set mood params
    mood_dict = {'any':{},
            'happy':{'min_energy':0.5,'min_valence':0.5},
            'chill':{'max_energy':0.5,'min_valence':0.5},
            'angry':{'min_energy':0.5,'max_valence':0.5},
            'sad' : {'max_energy':0.5,'max_valence':0.5}}
    mood = mood_dict[playlist_tuner['mood']]
    del playlist_tuner['mood']
    playlist_tuner.update(mood)

    if userIDs is not None:
        # load SQL table as DataFrame
        userTopTracks = ReadMySQL(userIDs)
        # filter by userIDs
        userTopTracks = userTopTracks[userTopTracks.user_id.isin(userIDs).values]
        # instantiate spotipy object spotify, userIDs and SQL user_top_tracks table into class
        SpotifyApp = SpotifyAPI(spotify, **{'sql2df':userTopTracks, 'userIDs':userIDs})

        # run make_playlist with playlist_tuner params
        del playlist_tuner['seed_genres']
        playlist_link = SpotifyApp.make_playlist(**playlist_tuner)
    else:
        # instantiate spotipy object spotify
        SpotifyApp = SpotifyAPI(spotify)
        # Step 1. get input() tuning parameters
        seed_genres = playlist_tuner['seed_genres'] if playlist_tuner['seed_genres'] != 'any' else None # needs default or random ... cannot get recs without any seeds
        del playlist_tuner['seed_genres']
        del playlist_tuner['release_date']
        # Step 2. get recommendations w/ .recommendations() using input tuning parameters as attributes
        recs = SpotifyApp.recommendations(seed_genres=seed_genres,**playlist_tuner)['tracks']
        # Step 3 & 4. create playlist and add tracks to playlist w/ .add_song_to_playlist()
        playlist_link = SpotifyApp.add_song_to_playlist([f"spotify:track:{x.get('id')}" for x in recs])

    return playlist_link