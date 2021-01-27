import pandas as pd
import spotipy

class SpotifyAPI(object): # passed object is the spotipy object with user oauth info ready for API

    def __init__(self, spotify, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spotify = spotify

    def current_user(self):
        return self.spotify.current_user()

    def current_user_top_artists(self, limit=50, offset=0, time_range='medium_term'):
        return self.spotify.current_user_top_artists(limit=limit, offset=offset, time_range=time_range)

    def current_user_top_tracks(self, limit=50, offset=0, time_range='medium_term'):
        return self.spotify.current_user_top_tracks(limit=limit, offset=offset, time_range=time_range)

    def get_user_top_tracks(self):
        df_list = []
        for term in ['medium_term','short_term','long_term']:
            top99 = pd.concat([
                pd.json_normalize(self.current_user_top_tracks(offset=0,time_range=term)['items'],sep='_'),
                pd.json_normalize(self.current_user_top_tracks(offset=49,time_range=term)['items'],sep='_')]).drop_duplicates(subset=['id'])
            top99.index = range(len(top99.index))
            top99['term_rank'] = top99.index+1
            top99['term'] = term
            df_list.append(top99)
        df = pd.concat(df_list)
        df['user_id'] = self.current_user()['id']
        df = df[['user_id','term','term_rank','id','name','popularity','album_release_date']]
        return df

# function that takes cache path and token code
def auth_n_code(session_cache_path,code):

    # set auth_manager
    user_auth_manager = spotipy.oauth2.SpotifyOAuth(scope='user-top-read',cache_path=session_cache_path)

    # insert code
    user_auth_manager.get_access_token(code)

    # set spotify client
    spotify = spotipy.Spotify(auth_manager=user_auth_manager)

    # get display name and user id
    display_name = spotify.me()["display_name"]
    user_id = spotify.me()["id"]

    # get user top tracks
    user_top_tracks_df = SpotifyAPI(spotify).get_user_top_tracks()

    return display_name, user_id, user_top_tracks_df
