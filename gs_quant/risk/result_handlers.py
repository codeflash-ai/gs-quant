"""
Copyright 2019 Goldman Sachs.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""
import datetime as dt
import logging
from typing import List, Iterable, Optional, Union

from gs_quant.base import InstrumentBase, RiskKey
from gs_quant.common import RiskMeasure, AssetClass, RiskMeasureType
from gs_quant.risk.measures import PnlExplain
from .core import DataFrameWithInfo, ErrorValue, UnsupportedValue, FloatWithInfo, SeriesWithInfo, StringWithInfo, \
    sort_values, MQVSValidatorDefnsWithInfo, MQVSValidatorDefn

_logger = logging.getLogger(__name__)


def __dataframe_handler(result: Iterable, mappings: tuple, risk_key: RiskKey, request_id: Optional[str] = None) \
        -> DataFrameWithInfo:
    # Collect rows as list for single pass, and empty test.
    result_list = list(result)
    if not result_list:
        return DataFrameWithInfo(risk_key=risk_key, request_id=request_id)

    # Only need to use the first row to determine columns
    first_row = result_list[0]

    # Prepare a mapping of destination-to-source so that source column names can be checked efficiently
    mappings_lookup = {v: k for k, v in mappings}
    first_row_keys = list(first_row.keys())
    indices: List[bool] = [src in mappings_lookup for src in first_row_keys]

    # Build up the ordered output columns as tuple (preserving original code comment and structure)
    columns = tuple(mappings_lookup[src] for src in first_row_keys if src in mappings_lookup)

    # Prepare the tuple generator for selected columns, using precomputed indices
    col_idxs = [i for i, keep in enumerate(indices) if keep]
    # Optimization: precompute col_idxs once, reduces per row overhead
    # This also preserves the input row column order as in original code

    # Efficient tuple extraction of selected values per row
    records_unsorted = (tuple(r[k] for k in first_row_keys if k in mappings_lookup) for r in result_list)
    # Sort using sort_values
    records = tuple(sort_values(records_unsorted, columns, columns))

    df = DataFrameWithInfo(records, risk_key=risk_key, request_id=request_id)
    df.columns = columns

    return df


def __dataframe_handler_unsorted(result: Iterable, mappings: tuple, date_cols: tuple, risk_key: RiskKey,
                                 request_id: Optional[str] = None) -> DataFrameWithInfo:
    result_list = list(result)
    if not result_list:
        return DataFrameWithInfo(risk_key=risk_key, request_id=request_id)

    # Produce one pass over result to build records
    field_froms = [m[1] for m in mappings]
    # This is roughly as efficient as possible without additional list comprehensions
    records = ([row.get(field) for field in field_froms] for row in result_list)

    df = DataFrameWithInfo(records, risk_key=risk_key, request_id=request_id)
    df.columns = [m[0] for m in mappings]
    if date_cols:
        # Only do the iteration if any date columns are present
        strptime = dt.datetime.strptime
        for dt_col in date_cols:
            # Using map with a local lambda for performance
            df[dt_col] = df[dt_col].map(lambda x: strptime(x, '%Y-%m-%d').date() if isinstance(x, str) else x)

    return df


def cashflows_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase, request_id: Optional[str] = None) \
        -> DataFrameWithInfo:
    mappings = (
        ('currency', 'currency'),
        ('payment_date', 'payDate'),
        ('set_date', 'setDate'),
        ('accrual_start_date', 'accStart'),
        ('accrual_end_date', 'accEnd'),
        ('payment_amount', 'payAmount'),
        ('notional', 'notional'),
        ('payment_type', 'paymentType'),
        ('floating_rate_option', 'index'),
        ('floating_rate_designated_maturity', 'indexTerm'),
        ('day_count_fraction', 'dayCountFraction'),
        ('spread', 'spread'),
        ('rate', 'rate'),
        ('discount_factor', 'discountFactor')
    )
    date_cols = ('payment_date', 'set_date', 'accrual_start_date', 'accrual_end_date')
    return __dataframe_handler_unsorted(result['cashflows'], mappings, date_cols, risk_key, request_id=request_id)


def error_handler(result: dict, risk_key: RiskKey, instrument: InstrumentBase, request_id: Optional[str] = None) \
        -> ErrorValue:
    error = result.get('errorString', 'Unknown error')
    if request_id:
        error += f'. request Id={request_id}'

    _logger.error(f'Error while computing {risk_key.risk_measure} on {instrument} for {risk_key.date}: {error}')
    return ErrorValue(risk_key, error, request_id=request_id)


def leg_definition_handler(result: dict, risk_key: RiskKey, instrument: InstrumentBase,
                           request_id: Optional[str] = None) -> InstrumentBase:
    return instrument.resolved(result, risk_key)


def message_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase, request_id: Optional[str] = None) \
        -> Union[StringWithInfo, ErrorValue]:
    message = result.get('message')
    if message is None:
        return ErrorValue(risk_key, "No result returned", request_id=request_id)
    else:
        return StringWithInfo(risk_key, message, request_id=request_id)


def number_and_unit_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                            request_id: Optional[str] = None) -> FloatWithInfo:
    return FloatWithInfo(risk_key, result.get('value', float('nan')), unit=result.get('unit'), request_id=request_id)


def required_assets_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                            request_id: Optional[str] = None) -> DataFrameWithInfo:
    mappings = (('mkt_type', 'type'), ('mkt_asset', 'asset'))
    return __dataframe_handler(result['requiredAssets'], mappings, risk_key, request_id=request_id)


def risk_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase, request_id: Optional[str] = None) \
        -> Union[DataFrameWithInfo, FloatWithInfo]:
    if result.get('children'):
        # result with leg valuations
        classes = []
        if result.get('val'):
            classes.append({'path': 'parent', 'value': result.get('val')})

        for key, val in result.get('children').items():
            classes.append({'path': key, 'value': val})
        mappings = (
            ('path', 'path'),
            ('value', 'value')
        )
        return __dataframe_handler(classes, mappings, risk_key, request_id=request_id)
    else:
        return FloatWithInfo(risk_key, result.get('val', float('nan')), unit=result.get('unit'), request_id=request_id)


def risk_by_class_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                          request_id: Optional[str] = None) -> Union[DataFrameWithInfo, FloatWithInfo]:
    # TODO Remove this once we migrate parallel USD IRDelta measures
    types = [c['type'] for c in result['classes']]
    # list of risk by class measures exposed in gs-quant
    external_risk_by_class_val = ['IRBasisParallel', 'IRDeltaParallel', 'IRVegaParallel', 'PnlExplain']
    if str(risk_key.risk_measure.name) in external_risk_by_class_val and len(types) <= 2 and len(set(types)) == 1:
        # The sum and tuple conversion is very efficient, nothing to optimize further
        return FloatWithInfo(risk_key, sum(result.get('values', (float('nan'),))), unit=result.get('unit'),
                             request_id=request_id)
    else:
        classes = []
        skip_set = set()

        rc_classes = result['classes']
        rc_values = result['values']

        # Move enumeration out of the loop for performance
        # Precompute crosses_idx up front
        crosses_idx = next((i for i, c in enumerate(rc_classes) if c['type'] == 'CROSSES'), None)

        # Inline and optimize the looping logic:
        # Avoid repeated append by using set for skip indices and list for classes
        for idx, (clazz, value) in enumerate(zip(rc_classes, rc_values)):
            mkt_type = clazz['type']
            if 'SPIKE' in mkt_type or 'JUMP' in mkt_type:
                skip_set.add(idx)
                if crosses_idx is not None:
                    rc_classes[crosses_idx]['value'] += value
            clazz['value'] = value  # Directly set instead of update for single key

        # Single scan for output, much faster than repeated 'if idx not in ...'
        for idx, clazz in enumerate(rc_classes):
            if idx not in skip_set:
                classes.append(clazz)

        mappings = (
            ('mkt_type', 'type'),
            ('mkt_asset', 'asset'),
            ('value', 'value')
        )

        if isinstance(risk_key.risk_measure, PnlExplain):
            return __dataframe_handler_unsorted(classes, mappings, (), risk_key, request_id=request_id)
        else:
            return __dataframe_handler(classes, mappings, risk_key, request_id=request_id)


def risk_vector_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                        request_id: Optional[str] = None) -> DataFrameWithInfo:
    assets = result['asset']
    # Handle equity risk measures which are really scalars
    if len(assets) == 1 and risk_key.risk_measure.name.startswith('Eq'):
        return FloatWithInfo(risk_key, assets[0], request_id=request_id)

    for points, value in zip(result['points'], assets):
        points.update({'value': value})

    mappings = (
        ('mkt_type', 'type'),
        ('mkt_asset', 'asset'),
        ('mkt_class', 'class_'),
        ('mkt_point', 'point'),
        ('mkt_quoting_style', 'quoteStyle'),
        ('value', 'value')
    )
    return __dataframe_handler(result['points'], mappings, risk_key, request_id=request_id)


def fixing_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                         request_id: Optional[str] = None) -> SeriesWithInfo:
    rows = result['fixingTableRows']

    dates = []
    values = []
    for row in rows:
        dates.append(dt.date.fromisoformat(row["fixingDate"]))
        values.append(row["fixing"])

    return SeriesWithInfo(values, index=dates, risk_key=risk_key, request_id=request_id)


def simple_valtable_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                            request_id: Optional[str] = None) -> DataFrameWithInfo:
    def get_value(value):
        handler = result_handlers.get(value.get('$type'))
        return handler(value, risk_key, _instrument, request_id)

    raw_res = result['rows']
    # simplevaltable's values contain all the information on units which needs to be extracted into the dataframe
    df = DataFrameWithInfo([(res['label'], get_value(res['value'])) for res in raw_res], risk_key=risk_key,
                           request_id=request_id, unit=raw_res[0]['value'].get('unit'))
    df.columns = ['label', 'value']
    return df


def canonical_projection_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                                       request_id: Optional[str] = None) -> DataFrameWithInfo:
    mappings = (
        ('asset_class', 'assetClass'),
        ('asset', 'asset'),
        ('asset_family', 'assetFamily'),
        ('asset_sub_family', 'assetSubFamily'),
        ('product', 'product'),
        ('product_family', 'productFamily'),
        ('product_sub_family', 'productSubFamily'),
        ('side', 'side'),
        ('size', 'size'),
        ('size_unit', 'sizeUnit'),
        ('quote_level', 'quoteLevel'),
        ('quote_unit', 'quoteUnit'),
        ('start_date', 'startDate'),
        ('end_date', 'endDate'),
        ('expiration_date', 'expiryDate'),
        ('strike', 'strike'),
        ('strike_unit', 'strikeUnit'),
        ('option_type', 'optionType'),
        ('option_style', 'optionStyle'),
        ('tenor', 'tenor'),
        ('tenor_unit', 'tenorUnit'),
        ('premium_currency', 'premiumCcy'),
        ('currency', 'currency')
    )
    date_cols = ('start_date', 'end_date', 'expiration_date')
    return __dataframe_handler_unsorted(result['rows'], mappings, date_cols, risk_key, request_id)


def risk_float_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                       request_id: Optional[str] = None) -> FloatWithInfo:
    return FloatWithInfo(risk_key, result['values'][0], request_id=request_id)


def map_coordinate_to_column(coordinate_struct, tag):
    updated_struct = {tag + "_" + k: v for k, v in coordinate_struct.items() if
                      k in ['type', 'asset', 'class_', 'point', 'quoteStyle']}
    raw_point = updated_struct.get('point', '')
    point = ';'.join(raw_point) if isinstance(raw_point, list) else raw_point
    updated_struct['point'] = point
    return updated_struct


def __is_single_row_2nd_order_risk(risk_key: RiskKey):
    return risk_key is not None and isinstance(risk_key.risk_measure,
                                               RiskMeasure) and \
        risk_key.risk_measure.asset_class == AssetClass.Rates and \
        risk_key.risk_measure.measure_type in (RiskMeasureType.ParallelGamma, RiskMeasureType.ParallelGammaLocalCcy)


def mdapi_second_order_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                                     request_id: Optional[str] = None) -> Union[DataFrameWithInfo, FloatWithInfo]:
    if len(result['values']) == 1 and __is_single_row_2nd_order_risk(risk_key):
        return risk_float_handler(result, risk_key, _instrument, request_id)

    coordinate_pairs = []

    if (len(result['innerPoints']) != len(result['outerPoints'])):
        raise Exception("Found inner and outer points of different size")

    for inner, outer, value in zip(result['innerPoints'], result['outerPoints'], result['values']):
        row_dict = dict(map_coordinate_to_column(inner, 'inner'), **map_coordinate_to_column(outer, 'outer'))
        row_dict.update({'value': value})
        coordinate_pairs.append(row_dict)

    mappings = (('inner_mkt_type', 'inner_type'),
                ('inner_mkt_asset', 'inner_asset'),
                ('inner_mkt_class', 'inner_class_'),
                ('inner_mkt_point', 'inner_point'),
                ('inner_mkt_quoting_style', 'inner_quotingStyle'),
                ('outer_mkt_type', 'outer_type'),
                ('outer_mkt_asset', 'outer_asset'),
                ('outer_mkt_class', 'outer_class_'),
                ('outer_mkt_point', 'outer_point'),
                ('outer_mkt_quoting_style', 'outer_quotingStyle'),
                ('value', 'value'),
                ('permissions', 'permissions'))

    return __dataframe_handler(coordinate_pairs, mappings, risk_key, request_id=request_id)


def mdapi_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                        request_id: Optional[str] = None) -> DataFrameWithInfo:
    coordinates = []
    for r in result['rows']:
        raw_point = r['coordinate'].get('point', '')
        point = ';'.join(raw_point) if isinstance(raw_point, list) else raw_point
        r['coordinate'].update({'point': point})
        r['coordinate'].update({'value': r.get('value', None)})
        r['coordinate'].update({'permissions': r['permissions']})
        coordinates.append(r['coordinate'])

    mappings = (('mkt_type', 'type'),
                ('mkt_asset', 'asset'),
                ('mkt_class', 'assetClass'),
                ('mkt_point', 'point'),
                ('mkt_quoting_style', 'quotingStyle'),
                ('value', 'value'),
                ('permissions', 'permissions'))

    return __dataframe_handler(coordinates, mappings, risk_key, request_id=request_id)


def mmapi_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                        request_id: Optional[str] = None) -> DataFrameWithInfo:
    coordinates = []
    for r in result['rows']:
        raw_point = r['modelCoordinate'].get('point', '')
        point = ';'.join(raw_point) if isinstance(raw_point, list) else raw_point
        r['modelCoordinate'].update({'point': point})
        raw_tags = r['modelCoordinate'].get('tags', '')
        tags = ';'.join(raw_tags) if isinstance(raw_tags, list) else raw_tags
        r['modelCoordinate'].update({'tags': tags})
        rows = r['value'].get('value', '')
        DataPoints = []
        for row in rows:
            DataPoints.append([dt.date.fromisoformat(row["date"]), row["value"]])
        r['modelCoordinate'].update({'value': DataPoints})
        coordinates.append(r['modelCoordinate'])

    mappings = (('mkt_type', 'type'),
                ('mkt_asset', 'asset'),
                ('mkt_point', 'point'),
                ('mkt_tags', 'tags'),
                ('mkt_quoting_style', 'quotingStyle'),
                ('value', 'value'))

    return __dataframe_handler(coordinates, mappings, risk_key, request_id=request_id)


def mmapi_pca_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                            request_id: Optional[str] = None) -> DataFrameWithInfo:
    coordinates = []
    for r in result['rows']:
        raw_point = r['coordinate'].get('point', '')
        point = ';'.join(raw_point) if isinstance(raw_point, list) else raw_point
        r['coordinate'].update({'point': point})
        r['coordinate'].update({'value': r['value']})
        r['coordinate'].update({'layer1': r['layer1']})
        r['coordinate'].update({'layer2': r['layer2']})
        r['coordinate'].update({'layer3': r['layer3']})
        r['coordinate'].update({'layer4': r['layer4']})
        r['coordinate'].update({'level': r['level']})
        r['coordinate'].update({'sensitivity': r['sensitivity']})
        r['coordinate'].update({'irDelta': r['irDelta']})
        r['coordinate'].update({'endDate': r['endDate']})
        coordinates.append(r['coordinate'])

    mappings = (('mkt_type', 'type'),
                ('mkt_asset', 'asset'),
                ('mkt_class', 'assetClass'),
                ('mkt_point', 'point'),
                ('mkt_quoting_style', 'quotingStyle'),
                ('value', 'value'),
                ('layer1', 'layer1'),
                ('layer2', 'layer2'),
                ('layer3', 'layer3'),
                ('layer4', 'layer4'),
                ('level', 'level'),
                ('sensitivity', 'sensitivity'),
                ('irDelta', 'irDelta'),
                ('endDate', 'endDate'))

    return __dataframe_handler(coordinates, mappings, risk_key, request_id=request_id)


def mmapi_pca_hedge_table_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                                  request_id: Optional[str] = None) -> DataFrameWithInfo:
    coordinates = []
    for r in result['rows']:
        raw_point = r['coordinate'].get('point', '')
        point = ';'.join(raw_point) if isinstance(raw_point, list) else raw_point
        r['coordinate'].update({'point': point})
        r['coordinate'].update({'size': r.get('size')})
        r['coordinate'].update({'fixedRate': r.get('fixedRate')})
        r['coordinate'].update({'irDelta': r.get('irDelta')})
        coordinates.append(r['coordinate'])
    mappings = (('mkt_type', 'type'),
                ('mkt_asset', 'asset'),
                ('mkt_class', 'assetClass'),
                ('mkt_point', 'point'),
                ('mkt_quoting_style', 'quotingStyle'),
                ('size', 'size'),
                ('fixedRate', 'fixedRate'),
                ('irDelta', 'irDelta'))

    return __dataframe_handler(coordinates, mappings, risk_key, request_id=request_id)


def mqvs_validators_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                            request_id: Optional[str] = None) -> MQVSValidatorDefnsWithInfo:
    validators = [MQVSValidatorDefn.from_dict(r) for r in result['validators']]
    return MQVSValidatorDefnsWithInfo(risk_key, tuple(validators), request_id=request_id)


def market_handler(result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                   request_id: Optional[str] = None) -> StringWithInfo:
    return StringWithInfo(risk_key, result.get('marketRef'), request_id=request_id)


def unsupported_handler(_result: dict, risk_key: RiskKey, _instrument: InstrumentBase,
                        request_id: Optional[str] = None) -> UnsupportedValue:
    return UnsupportedValue(risk_key, request_id=request_id)


result_handlers = {
    'Error': error_handler,
    'IRPCashflowTable': cashflows_handler,
    'LegDefinition': leg_definition_handler,
    'Message': message_handler,
    'MDAPITable': mdapi_table_handler,
    'MMAPITable': mmapi_table_handler,
    'MMAPIPCATable': mmapi_pca_table_handler,
    'MMAPIPCAHedgeTable': mmapi_pca_hedge_table_handler,
    'MQVSValidators': mqvs_validators_handler,
    'NumberAndUnit': number_and_unit_handler,
    'RequireAssets': required_assets_handler,
    'Risk': risk_handler,
    'RiskByClass': risk_by_class_handler,
    'RiskVector': risk_vector_handler,
    'FixingTable': fixing_table_handler,
    'Table': simple_valtable_handler,
    'CanonicalProjectionTable': canonical_projection_table_handler,
    'RiskSecondOrderVector': mdapi_second_order_table_handler,
    'RiskTheta': risk_float_handler,
    'Market': market_handler,
    'Unsupported': unsupported_handler
}
