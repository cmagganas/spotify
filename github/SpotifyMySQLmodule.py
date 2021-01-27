from sqlalchemy import create_engine
import pandas as pd

def DataFrame_to_sql(dataFrame, user_id):
    tableName = "user_top_tracks"
    sqlEngine = create_engine(
        "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
        username="",
        password="@RKcmPfzL4i8yks",
        hostname="",
        databasename=""
        ), pool_recycle=3600)
    dbConnection = sqlEngine.connect()

    sql = f"DELETE FROM user_top_tracks WHERE user_id = {user_id};"
    try:
        dbConnection.execute(sql)
    except:
        pass
    dataFrame.to_sql(tableName, dbConnection, if_exists='append');

    dbConnection.close()

def ReadMySQL(user_id):
    sqlEngine = create_engine(
        "mysql+mysqlconnector://{username}:{password}@{hostname}/{databasename}".format(
        username="",
        password="",
        hostname="",
        databasename=""
        ), pool_recycle=3600)
    dbConnection = sqlEngine.connect()
    if len(user_id)>1:
        sql = f"SELECT * FROM user_top_tracks WHERE user_id IN {tuple(user_id)};"
    else:
        sql = f"SELECT * FROM user_top_tracks WHERE user_id = '{user_id[0]}';"
    frame = pd.read_sql(sql, dbConnection);
    pd.set_option('display.expand_frame_repr', False)
    dbConnection.close()
    return frame