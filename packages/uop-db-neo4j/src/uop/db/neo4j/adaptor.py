from uop.core import db_collection as db_coll
from uop.core import database
from neo4j import GraphDatabase


class Neo4jCollection(db_coll.DBCollection):
    def __init__(self, collection_name, db_adaptor, indexed=False, constraint=None):
        super().__init__(collection_name, indexed=indexed)
        self._db = db_adaptor
        self._name = collection_name

    def insert(self, **object_data):
        label = self._name
        tenant_id = self._db._tenant_id
        with self._db.get_session() as session:
            result = session.execute_write(
                self._create_node, label, object_data, tenant_id
            )
            return result

    @staticmethod
    def _create_node(tx, label, properties, tenant_id):
        query = f"""
            MATCH (t:Tenant {{id: $tenant_id}})
            CREATE (n:{label} $properties)
            CREATE (n)-[:OWNS_OBJECT]->(t)
            RETURN n
        """
        result = tx.run(query, properties=properties, tenant_id=tenant_id)
        return result.single()[0]

    def find(
        self, criteria=None, only_cols=None, order_by=None, limit=None, ids_only=False
    ):
        label = self._name
        tenant_id = self._db._tenant_id
        with self._db.get_session() as session:
            result = session.execute_read(
                self._match_nodes,
                label,
                criteria,
                only_cols,
                order_by,
                limit,
                tenant_id,
            )
            return result

    @staticmethod
    def _match_nodes(tx, label, criteria, only_cols, order_by, limit, tenant_id):
        query = f"MATCH (t:Tenant {{id: $tenant_id}})<-[:OWNS_OBJECT]-(n:{label})"
        parameters = {"tenant_id": tenant_id}

        if criteria:
            where_clauses = []
            for key, value in criteria.items():
                where_clauses.append(f"n.{key} = ${key}")
                parameters[key] = value
            query += " WHERE " + " AND ".join(where_clauses)

        if only_cols:
            query += f" RETURN {', '.join(['n.' + col for col in only_cols])}"
        else:
            query += " RETURN n"

        if order_by:
            query += f" ORDER BY {', '.join(['n.' + col for col in order_by])}"

        if limit:
            query += f" LIMIT {limit}"

        result = tx.run(query, **parameters)
        return [record for record in result]

    def update(self, criteria, mods, partial=True):
        label = self._name
        tenant_id = self._db._tenant_id
        with self._db.get_session() as session:
            session.execute_write(
                self._update_nodes, label, criteria, mods, partial, tenant_id
            )

    @staticmethod
    def _update_nodes(tx, label, criteria, mods, partial, tenant_id):
        query = f"MATCH (t:Tenant {{id: $tenant_id}})<-[:OWNS_OBJECT]-(n:{label})"
        parameters = {"tenant_id": tenant_id}

        if criteria:
            where_clauses = []
            for key, value in criteria.items():
                where_clauses.append(f"n.{key} = ${key}")
                parameters[key] = value
            query += " WHERE " + " AND ".join(where_clauses)

        if partial:
            set_clauses = []
            for key, value in mods.items():
                set_clauses.append(f"n.{key} = ${key}")
                parameters[key] = value
            query += " SET " + ", ".join(set_clauses)
        else:
            query += " SET n = $mods"
            parameters["mods"] = mods

        tx.run(query, **parameters)

    def remove(self, dict_or_key):
        label = self._name
        tenant_id = self._db._tenant_id
        with self._db.get_session() as session:
            session.execute_write(self._delete_nodes, label, dict_or_key, tenant_id)

    @staticmethod
    def _delete_nodes(tx, label, dict_or_key, tenant_id):
        query = f"MATCH (t:Tenant {{id: $tenant_id}})<-[:OWNS_OBJECT]-(n:{label})"
        parameters = {"tenant_id": tenant_id}

        if isinstance(dict_or_key, dict):
            where_clauses = []
            for key, value in dict_or_key.items():
                where_clauses.append(f"n.{key} = ${key}")
                parameters[key] = value
            query += " WHERE " + " AND ".join(where_clauses)
        else:
            query += " WHERE n.id = $id"
            parameters["id"] = dict_or_key

        query += " DETACH DELETE n"
        tx.run(query, **parameters)


class Neo4jUOP(database.Database):
    @classmethod
    def make_named_database(cls, name, **kwargs):
        return cls(dbname=name, **kwargs)

    def drop_database(self):
        with self.get_session() as session:
            session.run(f"DROP DATABASE {self._db_name} IF EXISTS")

    def __init__(self, dbname, tenant_id=None, *schemas, **kwargs):
        self._db_name = dbname
        self._driver = None
        self._tenant_id = tenant_id  # Store tenant_id
        self._tx = None
        super().__init__(tenant_id=tenant_id, *schemas, **kwargs)

    def open_db(self):
        uri = self._credentials.get("uri", "bolt://localhost:7687")
        user = self._credentials.get("user", "neo4j")
        password = self._credentials.get("password", "testpassword")
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        super().open_db()

    def close(self):
        if self._driver:
            self._driver.close()

    def get_session(self):
        return self._driver.session(database=self._db_name)

    def get_raw_collection(self, name, schema=None):
        # For Neo4j, a "collection" is a label.
        # This method can be a no-op, as labels are created when nodes are created.
        return name

    def wrap_raw_collection(self, raw):
        return Neo4jCollection(raw, self)

    def begin_transaction(self):
        if not hasattr(self, "_tx") or self._tx is None:
            self._tx = self._driver.session(database=self._db_name).begin_transaction()
        return self._tx

    def commit(self):
        if hasattr(self, "_tx") and self._tx is not None:
            self._tx.commit()
            self._tx = None

    def rollback_transaction(self):
        if hasattr(self, "_tx") and self._tx is not None:
            self._tx.rollback()
            self._tx = None

    def get_metadata(self):
        from uop.core.collections import meta_kinds

        metadata = {}
        with self.get_session() as session:
            for kind in meta_kinds:
                label = kind.capitalize()
                query = f"""
                    MATCH (t:Tenant {{id: $tenant_id}})<-[:OWNED_BY]-(n:{label})
                    RETURN n
                """
                result = session.run(query, tenant_id=self._tenant_id)
                metadata[kind] = [record["n"] for record in result]
        return metadata

    def apply_changes(self, changeset):
        from uop.core.collections import crud_kinds

        tx = self.begin_transaction()
        try:
            # Ensure tenant node exists
            if self._tenant_id:
                tx.run("MERGE (t:Tenant {id: $tenant_id})", tenant_id=self._tenant_id)

            # Process meta object changes
            for kind in crud_kinds:
                changes = getattr(changeset, kind)
                label = kind.capitalize()

                for key, props in changes.inserted.items():
                    query = f"""
                        MATCH (t:Tenant {{id: $tenant_id}})
                        MERGE (n:{label} {{id: $key}})
                        SET n += $props
                        MERGE (n)-[:OWNED_BY]->(t)
                    """
                    tx.run(query, key=key, props=props, tenant_id=self._tenant_id)

                for key, props in changes.modified.items():
                    query = f"""
                        MATCH (t:Tenant {{id: $tenant_id}})<-[:OWNED_BY]-(n:{label} {{id: $key}})
                        SET n += $props
                    """
                    tx.run(query, key=key, props=props, tenant_id=self._tenant_id)

                for key in changes.deleted:
                    query = f"""
                        MATCH (t:Tenant {{id: $tenant_id}})<-[:OWNED_BY]-(n:{label} {{id: $key}})
                        DETACH DELETE n
                    """
                    tx.run(query, key=key, tenant_id=self._tenant_id)

            # Process relationship changes
            related_changes = changeset.related
            for related in related_changes.inserted:
                role_name = self.id_to_name("roles").get(related.assoc_id, "RELATED_TO")
                tx.run(
                    f"""
                    MATCH (subject {{id: $subject_id}}), (object {{id: $object_id}})
                    MERGE (subject)-[r:{role_name}]->(object)
                    """,
                    subject_id=related.subject_id,
                    object_id=related.object_id,
                )

            for related in related_changes.deleted:
                role_name = self.id_to_name("roles").get(related.assoc_id, "RELATED_TO")
                tx.run(
                    f"""
                    MATCH (subject {{id: $subject_id}})-[r:{role_name}]->(object {{id: $object_id}})
                    DELETE r
                    """,
                    subject_id=related.subject_id,
                    object_id=related.object_id,
                )

            self.commit()
            self.reload_metacontext()

        except Exception as e:
            self.rollback_transaction()
            raise e

    def relate(self, subject_oid, roleid, object_oid):
        role_name = self.id_to_name("roles").get(roleid, "RELATED_TO")
        query = f"""
            MATCH (subject {{id: $subject_id}}), (object {{id: $object_id}})
            MERGE (subject)-[:{role_name}]->(object)
            """
        params = {"subject_id": subject_oid, "object_id": object_oid}

        if self._tx:
            self._tx.run(query, **params)
        else:
            with self.get_session() as session:
                session.run(query, **params)

    def unrelate(self, subject_oid, roleid, object_oid):
        role_name = self.id_to_name("roles").get(roleid, "RELATED_TO")
        query = f"""
            MATCH (subject {{id: $subject_id}})-[r:{role_name}]->(object {{id: $object_id}})
            DELETE r
            """
        params = {"subject_id": subject_oid, "object_id": object_oid}

        if self._tx:
            self._tx.run(query, **params)
        else:
            with self.get_session() as session:
                session.run(query, **params)

    def get_roleset(self, subject, role_id, reverse=False):
        role_name = self.id_to_name("roles").get(role_id, "RELATED_TO")

        if reverse:
            query = f"""
                MATCH (object)-[:{role_name}]->(subject {{id: $subject_id}})
                RETURN object.id
            """
        else:
            query = f"""
                MATCH (subject {{id: $subject_id}})-[:{role_name}]->(object)
                RETURN object.id
            """

        params = {"subject_id": subject}

        if self._tx:
            result = self._tx.run(query, **params)
        else:
            with self.get_session() as session:
                result = session.run(query, **params)

        return {record["object.id"] for record in result}
