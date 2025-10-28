import datetime as dt
from typing import List, Optional

import pandas as pd
from codeflash.verification.codeflash_capture import codeflash_capture
from pydash import get

from gs_quant.api.gs.assets import GsAsset, GsAssetApi
from gs_quant.data import Dataset
from gs_quant.errors import MqValueError

'\nCopyright 2019 Goldman Sachs.\nLicensed under the Apache License, Version 2.0 (the "License");\nyou may not use this file except in compliance with the License.\nYou may obtain a copy of the License at\n\n  http://www.apache.org/licenses/LICENSE-2.0\n\nUnless required by applicable law or agreed to in writing,\nsoftware distributed under the License is distributed on an\n"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY\nKIND, either express or implied.  See the License for the\nspecific language governing permissions and limitations\nunder the License.\n'

class AssetTreeNode:

    @codeflash_capture(function_name='AssetTreeNode.__init__', tmp_dir_path='/tmp/codeflash_rlzdl1lh/test_return_values', tests_root='/home/ubuntu/work/repo/gs_quant/test', is_fto=True)
    def __init__(self, id, depth: Optional[int]=0, date: Optional[dt.date]=None, asset: Optional[GsAsset]=None):
        self.id = id
        self.date = date
        self.depth = depth
        self.asset = asset
        self.name = get(self.asset, 'name')
        self.bbid = get(get(self.asset, 'xref'), 'bbid')
        self.asset_type = get(self.asset, 'type')
        self.data = {}
        self.constituents_df = pd.DataFrame()
        self.direct_underlier_assets_as_nodes = []

    def __str__(self):
        result = self.bbid if self.bbid is not None else self.id
        return f'Tree Node - {result}'

    def to_frame(self) -> pd.DataFrame:
        if len(self.constituents_df) > 0:
            return self.constituents_df
        else:
            all_rows = self.__gather_constituents_rows()
            # Use .from_records for efficiency and avoid unneeded copy
            df = pd.DataFrame.from_records(all_rows)
            if not df.empty:
                # Use sort_values' inplace for lower memory use. 
                # Reset index before drop_duplicates to avoid unnecessary memory realloc.
                df.reset_index(drop=True, inplace=True)
                df.drop_duplicates(inplace=True)
                df.sort_values(by='depth', inplace=True)
                df.reset_index(drop=True, inplace=True)
            self.constituents_df = df
            return self.constituents_df

    def populate_values(self, dataset, value_column, underlier_column):
        ds = Dataset(dataset)
        query = ds.get_data(start=self.date, end=self.date, assetId=[self.id])
        if len(query) > 0:
            for node in self.direct_underlier_assets_as_nodes:
                value = query.loc[query[underlier_column] == node.id][value_column].iloc[0]
                node.data[value_column] = value
                node.populate_values(dataset, value_column, underlier_column)

    def build_tree(self, dataset, underlier_column):
        """
        Build the full tree and return the root node
        """
        query = self.__get_direct_underliers(self.id, dataset)
        if len(query) > 0:
            all_ids = query[underlier_column].tolist()
            all_assets = GsAssetApi.get_many_assets(id=all_ids)
            asset_lookup = {mq_id: asset_obj for (mq_id, asset_obj) in zip(all_ids, all_assets)}
            for (i_, row) in query.iterrows():
                underlier = row[underlier_column]
                if underlier not in asset_lookup:
                    raise Exception('Unable to find {}'.format(underlier))
                child_node = AssetTreeNode(underlier, self.depth + 1, self.date, asset_lookup[underlier])
                child_node.build_tree(dataset, underlier_column)
                self.direct_underlier_assets_as_nodes.append(child_node)

    def __get_direct_underliers(self, asset_id, dataset) -> pd.DataFrame:
        """
        Queries the dataset for the date passed during initialisation. If date isn't passed, returns the data of the
        latest available date.
        """
        ds = Dataset(dataset)
        if self.date:
            query = ds.get_data(start=self.date, end=self.date, assetId=[asset_id]).drop_duplicates()
        else:
            query = ds.get_data(assetId=[asset_id]).drop_duplicates()
        if len(query) > 0:
            self.date = query.index.max().date()
            query = query[query.index == query.index.max()].reset_index()
        return query

    def __build_constituents_df(self, constituents_df) -> pd.DataFrame:
        for node in self.direct_underlier_assets_as_nodes:
            data = {'date': self.date, 'assetName': self.name, 'assetId': self.id, 'assetBbid': self.bbid, 'underlyingAssetName': node.name, 'underlyingAssetId': node.id, 'underlyingAssetBbid': node.bbid, 'depth': node.depth}
            for (key, value) in node.data.items():
                data[key] = value
            constituents_df = constituents_df.append(pd.DataFrame(data, index=[0]))
            d = node.__build_constituents_df(pd.DataFrame())
            if len(d) > 0:
                constituents_df = constituents_df.append(d)
        return constituents_df

    def __gather_constituents_rows(self) -> List[dict]:
        # Use list object append/extend in outer-scope for generator instead of comprehension with temporary list
        rows = []
        stack = [(node, self) for node in self.direct_underlier_assets_as_nodes]
        extend = stack.extend  # localize for faster lookup in hot loop
        append = rows.append   # localize for faster lookup in hot loop
        while stack:
            node, parent = stack.pop()
            data = {
                'date': parent.date,
                'assetName': parent.name,
                'assetId': parent.id,
                'assetBbid': parent.bbid,
                'underlyingAssetName': node.name,
                'underlyingAssetId': node.id,
                'underlyingAssetBbid': node.bbid,
                'depth': node.depth
            }
            # Use dict.update instead of for loop for performance
            data.update(node.data)
            append(data)
            # Avoid generator expression allocation by direct loop
            # but to keep stack extend performance, stay with generator expression
            extend(((child, node) for child in node.direct_underlier_assets_as_nodes))
        return rows

class TreeHelper:

    def __init__(self, id, date: Optional[dt.date]=None, tree_underlier_dataset: Optional[str]=None, underlier_column: Optional[str]='underlyingAssetId'):
        self.id = id
        self.root = AssetTreeNode(self.id, 0, date, GsAssetApi.get_asset(asset_id=self.id))
        self.date = self.root.date
        self.update_time = dt.datetime.now()
        self.constituents_df = pd.DataFrame()
        self.tree_built = False
        self.__tree_underlier_dataset = tree_underlier_dataset
        self.__underlier_column = underlier_column

    def populate_weights(self, dataset, weight_column: Optional[str]='weight'):
        if not self.tree_built:
            self.build_tree()
        self.root.data['weight'] = 1
        self.root.populate_values(dataset, weight_column, self.__underlier_column)

    def populate_attribution(self, dataset, attribution_column: Optional[str]='absoluteAttribution'):
        if not self.tree_built:
            self.build_tree()
        self.root.data['absoluteAttribution'] = 1
        self.root.populate_values(dataset, attribution_column, self.__underlier_column)

    def to_frame(self) -> pd.DataFrame:
        """
        Retrieve constituents of the full tree. If it has already been fetched once, it is stored and returned when
        called later in the future.

        :return: dataframe with constituents of the full tree, with parent AssetID, underlying AssetID, depth and weight

        **Usage**

        Retrieve constituents of the full tree.
        """
        if not self.tree_built:
            self.build_tree()
        self.constituents_df = self.root.to_frame()
        if len(self.constituents_df) > 0:
            return self.constituents_df
        else:
            raise MqValueError('No constituents found for the asset')

    def build_tree(self):
        if not self.tree_built:
            self.root.build_tree(self.__tree_underlier_dataset, self.__underlier_column)
            self.tree_built = True
            self.update_time = dt.datetime.now()

    def get_tree(self) -> AssetTreeNode:
        """
        Build the full tree and return the root node of the full-fledged tree.
        If the tree has been built already, return it on future calls.

        :return: AssetTreeNode object of the root node, with a list attribute direct_underlier_assets_as_nodes that
        holds the child AssetTreeNode object.

        **Usage**

        Root AssetTreeNode object of the tree entity
        """
        if not self.tree_built:
            self.build_tree()
        return self.root

    def get_visualisation(self, visualise_by: str='name'):
        try:
            from treelib import Tree
        except ModuleNotFoundError:
            raise RuntimeError('You must install treelib to be able use this function.')
        if not self.tree_built:
            self.build_tree()
        if visualise_by in ['name', 'bbid', 'id']:
            bfs_queue = [[self.root, '']]
            tree_vis = Tree()
            while len(bfs_queue) != 0:
                (node, prefix) = bfs_queue.pop(0)
                node_id = prefix + '-' + node.id
                node_name = getattr(node, visualise_by)
                if str(node_name) == 'None':
                    node_name = f'NA ({node.id})'
                if prefix == '':
                    tree_vis.create_node(node_name, node_id)
                else:
                    tree_vis.create_node(node_name, node_id, parent=prefix)
                for c in node.direct_underlier_assets_as_nodes:
                    bfs_queue.append([c, node_id])
        else:
            raise MqValueError('visualise_by argument has to be either name, id or bbid')
        return tree_vis.show()
