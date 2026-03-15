# Repositório para simular um banco de dados enquanto o final não fica pronto
import csv
import json
import collections.abc
from typing import List, Dict, Any, Optional
from datetime import date

TECNICOS_CSV = 'tecnicos_db.csv'
CHAMADOS_CSV = 'chamados_db.csv'


def deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def json_converter(o):
    if isinstance(o, date):
        return o.isoformat()
    return None


class InMemoryRepository:
    def __init__(self, collection_name: str):
        self._collection_name = collection_name
        self._csv_file = f"{collection_name}_db.csv"
        self._collection = self._load_from_csv()
        if self._collection:
            self._next_id = max(int(item.get('id', 0)) for item in self._collection) + 1
        else:
            self._next_id = 1

    def _load_from_csv(self) -> List[Dict[str, Any]]:
        try:
            with open(self._csv_file, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                data = []
                for row in reader:

                    int_fields = ['id', 'cliente_id', 'id_tecnico_atribuido',
                                  'codigo']  # Resolve os problemas de ints tratadas como strings
                    for field in int_fields:
                        if field in row:
                            value = row[field]
                            if value == '':
                                row[field] = None
                            else:
                                try:
                                    row[field] = int(row[field])
                                except (ValueError, TypeError):
                                    row[field] = None

                    json_fields = ['dados_bancarios', 'cliente', 'visitas', 'materiais_utilizados', "contato_principal",
                                   'comprovante_pedagio_urls',
                                   'comprovante_frete_urls']  # Resolve os problemas de JSON aninhado que são tratados como strings
                    for field in json_fields:
                        if field in row and row[field]:
                            try:
                                row[field] = json.loads(row[field])
                            except json.JSONDecodeError:
                                pass

                    bool_fields = ['is_active', 'is_cancelled',
                                   'em_garantia']  # Resolve os problemas de booleans sendo tratados como strings
                    for field in bool_fields:
                        if field in row:
                            row[field] = row[field] == 'True'

                    optional_date_fields = ['data_conclusao', 'data_faturamento', 'data_agendamento']
                    for field in optional_date_fields:
                        if field in row and row[field] == '':
                            row[field] = None

                    data.append(row)
                return data
        except FileNotFoundError:
            return []

    def _save_to_csv(self):
        if not self._collection:
            return

        data_to_save = []
        for item in self._collection:
            item_copy = item.copy()
            for key, value in item_copy.items():
                if isinstance(value, (dict, list)):
                    item_copy[key] = json.dumps(value, default=json_converter)
            data_to_save.append(item_copy)

        with open(self._csv_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=data_to_save[0].keys())
            writer.writeheader()
            writer.writerows(data_to_save)

    def create(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        item_data["id"] = self._next_id
        self._collection.append(item_data)
        self._next_id += 1
        self._save_to_csv()
        return item_data

    def get_all(self, is_active: Optional[bool] = None) -> List[Dict[str, Any]]:
        if is_active is None:
            return self._collection
        return [item for item in self._collection if item.get('is_active') == is_active]

    def get_by_id(self, item_id: int) -> Dict[str, Any] | None:
        for item in self._collection:
            if item.get("id") == item_id:
                return item
        return None

    def update(self, item_id: int, item_data: Dict[str, Any]) -> Dict[str, Any] | None:
        item_to_update = self.get_by_id(item_id)
        if item_to_update is None:
            return None

        updated_item = deep_update(item_to_update, item_data)
        self._save_to_csv()
        return updated_item

    def delete(self, item_id: int) -> bool:
        item_to_deactivate = self.get_by_id(item_id)
        if item_to_deactivate is None:
            return False

        if 'is_active' in item_to_deactivate:
            item_to_deactivate['is_active'] = False
        if 'is_cancelled' in item_to_deactivate:
            item_to_deactivate['is_cancelled'] = True

        self._save_to_csv()
        return True
