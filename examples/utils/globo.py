import datetime
import numpy as np
import pandas as pd


def read_articles(path: str) -> pd.DataFrame:
    articles_df = pd.read_parquet(path)

    articles_df["category"] = "news"
    articles_df["subcategory"] = articles_df["topics"].apply(
        lambda row: [] if len(row) == 0 else row[0]
    )

    articles_df["cat_subcat"] = articles_df["topics"]
    articles_df.rename(
        columns={"newsID": "newsid", "topics": "cat_as_list"}, inplace=True
    )
    print("Nr of unique articles", articles_df.newsid.unique().size)
    return articles_df


def text_to_array(text: pd.Series, rgx_exp: str) -> pd.Series:
    return str(text).split(rgx_exp)


def read_behavior(path: str) -> pd.DataFrame:
    behaviors_presel_df = pd.read_parquet(path)
    behaviors_presel_df.rename(
        columns={
            "impressionId": "index",
            "history": "behavior_array",
            "impressions": "pool_array",
            "userId": "user",
        },
        inplace=True,
    )
    behaviors_presel_df["datetime"] = behaviors_presel_df["impressionTimestamp"].apply(
        lambda x: datetime.datetime.fromtimestamp(x / 1000)
    )
    return behaviors_presel_df


def get_top_rec_ids_array(
    pred_df: pd.DataFrame, behaviors_presel_df: pd.DataFrame, top_k: int
) -> pd.DataFrame:
    # Create a df with one row per user that contains only the top_k recommendations, that is the newsid and not the position of the preselection

    pred_df = pred_df[pred_df["size_list"] >= top_k]
    pred_preselection_df = pred_df.merge(
        behaviors_presel_df[["index", "user", "pool_array"]], on="index"
    )
    pred_preselection_df["pred_slice_id"] = pred_preselection_df.apply(
        (
            lambda x: [
                str(x["pool_array"][indx]) for indx, ele in enumerate(x["pred_rank"])
            ]
        ),
        axis=1,
    )
    pred_preselection_df = pred_preselection_df.drop(
        ["pool_array", "pred_rank"], axis=1
    )
    return pred_preselection_df


def read_predictions(
    path_predictions: str, behaviors_presel_df: pd.DataFrame, top_k: int, algo: str
) -> tuple:
    pred_df = pd.read_parquet(path_predictions)
    pred_df["pred_rank"] = pred_df["impressions"]
    pred_df = pred_df.rename(columns={"impr_index": "index"})
    pred_df.drop(columns=["impressions", "positions"], inplace=True)
    pred_df["size_list"] = pred_df["pred_rank"].apply(len)
    pred_df["algo"] = algo
    pred_preselection_df = get_top_rec_ids_array(
        pred_df, behaviors_presel_df, top_k=2 * top_k
    )
    return pred_df, pred_preselection_df


def get_cat(
    df: pd.DataFrame,
    articles_df: pd.DataFrame,
    column: str,
    cat_column: str,
    top_at: int,
    slice_col: bool = False,
    size_cat_list: int = 2,
) -> pd.DataFrame:
    s = pd.DataFrame(
        {column: np.concatenate(df[column].values)},
        index=df.index.repeat(df[column].str.len()),
    )
    df_exploded = s.join(df.drop(column, axis=1), how="left")
    df_exploded["rank"] = df_exploded.groupby(
        df_exploded.index
    ).cumcount()  # +1 # commented out because rank is related to the index of a list
    df_exploded = df_exploded.rename(columns={column: "newsid"})

    articles_df_thin = articles_df[["newsid", cat_column]].copy(deep=True)
    articles_df_thin[cat_column] = articles_df_thin[cat_column].apply(tuple)
    articles_df_thin = articles_df_thin.drop_duplicates()
    articles_df_thin[cat_column] = articles_df_thin[cat_column].apply(list)

    df_cat = df_exploded.merge(articles_df_thin, on="newsid", how="inner")

    df_cat = df_cat.sort_values(by=["index", "rank"])
    df_cat1 = (
        df_cat.groupby("index")[cat_column]
        .apply(list)
        .reset_index(name="sorted_cat_list")
    )
    df_cat2 = (
        df_cat.groupby("index")["newsid"]
        .apply(list)
        .reset_index(name="sorted_newsid_list")
    )
    df_cat = df_cat1.merge(df_cat2, on="index")

    df_cat = df_cat.merge(df.drop(column, axis=1), on="index")
    if slice_col:
        df_cat["size_newsid_list"] = df_cat["sorted_newsid_list"].apply(len)
        df_cat = df_cat[df_cat["size_newsid_list"] >= 10]
        df_cat["sorted_cat_list"] = df_cat.apply(
            lambda row: list(row["sorted_cat_list"])[0:top_at], axis=1
        )
        df_cat["sorted_newsid_list"] = df_cat.apply(
            lambda row: list(row["sorted_newsid_list"])[0:top_at], axis=1
        )
        df_cat["size_cat_list"] = df_cat["sorted_cat_list"].apply(len)
        df_cat = df_cat[df_cat["size_cat_list"] >= size_cat_list]
    return df_cat
