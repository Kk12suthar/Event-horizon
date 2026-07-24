--
-- PostgreSQL database dump
--

\restrict PfA4WKwRZgOid20uuubR095AvNMwvU1I1ITANCwyEoVNCkwG9EJhaIJz5f8059O

-- Dumped from database version 16.10
-- Dumped by pg_dump version 16.10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: charts_storage; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA charts_storage;


--
-- Name: instance01; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA instance01;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: chart_storage; Type: TABLE; Schema: charts_storage; Owner: -
--

CREATE TABLE charts_storage.chart_storage (
    chart_id character varying(36) NOT NULL,
    chart_type character varying(50) NOT NULL,
    chart_title character varying(255) NOT NULL,
    chart_data jsonb NOT NULL,
    chart_config jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    query_hash character varying(64)
);


--
-- Name: admin_audit_logs; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.admin_audit_logs (
    id integer NOT NULL,
    action_type character varying(50) NOT NULL,
    actor_id character varying(64),
    target_type character varying(50),
    target_id character varying(256),
    details jsonb,
    "timestamp" timestamp with time zone DEFAULT now()
);


--
-- Name: admin_audit_logs_id_seq; Type: SEQUENCE; Schema: instance01; Owner: -
--

CREATE SEQUENCE instance01.admin_audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admin_audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: instance01; Owner: -
--

ALTER SEQUENCE instance01.admin_audit_logs_id_seq OWNED BY instance01.admin_audit_logs.id;


--
-- Name: agent_model_config; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.agent_model_config (
    id text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    encrypted_api_key text,
    base_url text,
    site_url text,
    app_name text,
    temperature numeric,
    updated_by text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: data_collection; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.data_collection (
    id uuid NOT NULL,
    title character varying(100) NOT NULL,
    data jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by uuid NOT NULL
);


--
-- Name: mtd_access; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_access (
    id integer NOT NULL,
    entity_id uuid NOT NULL,
    entity_type character varying(20) NOT NULL,
    user_id character varying(128) NOT NULL,
    level character varying(20) NOT NULL,
    granted_date timestamp without time zone NOT NULL,
    granted_by character varying(128) NOT NULL,
    expiration_date timestamp without time zone
);


--
-- Name: mtd_access_id_seq; Type: SEQUENCE; Schema: instance01; Owner: -
--

CREATE SEQUENCE instance01.mtd_access_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mtd_access_id_seq; Type: SEQUENCE OWNED BY; Schema: instance01; Owner: -
--

ALTER SEQUENCE instance01.mtd_access_id_seq OWNED BY instance01.mtd_access.id;


--
-- Name: mtd_dashboard; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_dashboard (
    id uuid NOT NULL,
    name character varying(50) NOT NULL,
    description character varying(100),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(128) NOT NULL,
    status character varying(20) NOT NULL,
    parent_folder_id uuid NOT NULL,
    layout_config jsonb
);


--
-- Name: mtd_file; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_file (
    id uuid NOT NULL,
    name character varying(50) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    uploaded_by character varying(128) NOT NULL,
    status character varying(20) NOT NULL,
    parent_folder_id uuid NOT NULL,
    original_name character varying(100)
);


--
-- Name: mtd_folder; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_folder (
    id uuid NOT NULL,
    name character varying(50) NOT NULL,
    description character varying(100),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(128) NOT NULL,
    status character varying(20) NOT NULL,
    project_id uuid NOT NULL,
    entities jsonb
);


--
-- Name: mtd_project; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_project (
    id uuid NOT NULL,
    name character varying(50) NOT NULL,
    description character varying(255),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(128) NOT NULL,
    status character varying(20) NOT NULL
);


--
-- Name: mtd_results; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_results (
    type character varying(20) NOT NULL,
    id uuid NOT NULL,
    table_id uuid NOT NULL,
    session_id uuid NOT NULL,
    data jsonb
);


--
-- Name: mtd_session; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_session (
    id uuid NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(128) NOT NULL,
    status character varying(20) NOT NULL,
    folder_id uuid NOT NULL,
    app_name character varying(45) NOT NULL
);


--
-- Name: mtd_session_artifact; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_session_artifact (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    folder_id uuid NOT NULL,
    artifact_type character varying(32) NOT NULL,
    status character varying(32) DEFAULT 'ready'::character varying NOT NULL,
    name text NOT NULL,
    source_table_id text,
    transform_revision integer DEFAULT 0 NOT NULL,
    format character varying(16),
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    storage_path text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT mtd_session_artifact_type_check CHECK (((artifact_type)::text = ANY ((ARRAY['transform_table'::character varying, 'chart'::character varying, 'report'::character varying, 'report_draft'::character varying])::text[])))
);


--
-- Name: mtd_session_workspace; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_session_workspace (
    session_id uuid NOT NULL,
    folder_id uuid NOT NULL,
    selected_table_id text,
    selected_table_name text,
    transform_revision integer DEFAULT 0 NOT NULL,
    transform_status character varying(32) DEFAULT 'EMPTY'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: mtd_table; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_table (
    id uuid NOT NULL,
    name character varying(45) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(128) NOT NULL,
    parent_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    type character varying(10) NOT NULL
);


--
-- Name: mtd_user_invitations; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_user_invitations (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    role character varying(50) DEFAULT 'VIEWER'::character varying NOT NULL,
    invited_by character varying(128) NOT NULL,
    invite_token character varying(255) NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    accepted_at timestamp without time zone
);


--
-- Name: mtd_users; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_users (
    id character varying(128) NOT NULL,
    name character varying(150) NOT NULL,
    email character varying(320) NOT NULL,
    role character varying(20) NOT NULL
);


--
-- Name: mtd_variant_analysis_cache; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.mtd_variant_analysis_cache (
    table_name character varying(255) NOT NULL,
    analysis_data jsonb,
    row_count bigint,
    created_at timestamp without time zone DEFAULT (now() AT TIME ZONE 'utc'::text),
    updated_at timestamp without time zone DEFAULT (now() AT TIME ZONE 'utc'::text)
);


--
-- Name: upload_locks; Type: TABLE; Schema: instance01; Owner: -
--

CREATE TABLE instance01.upload_locks (
    folder_id character varying(64) NOT NULL,
    user_id character varying(64) NOT NULL,
    username character varying(100) NOT NULL,
    locked_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: admin_audit_logs id; Type: DEFAULT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.admin_audit_logs ALTER COLUMN id SET DEFAULT nextval('instance01.admin_audit_logs_id_seq'::regclass);


--
-- Name: mtd_access id; Type: DEFAULT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_access ALTER COLUMN id SET DEFAULT nextval('instance01.mtd_access_id_seq'::regclass);


--
-- Name: chart_storage chart_storage_pkey; Type: CONSTRAINT; Schema: charts_storage; Owner: -
--

ALTER TABLE ONLY charts_storage.chart_storage
    ADD CONSTRAINT chart_storage_pkey PRIMARY KEY (chart_id);


--
-- Name: admin_audit_logs admin_audit_logs_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.admin_audit_logs
    ADD CONSTRAINT admin_audit_logs_pkey PRIMARY KEY (id);


--
-- Name: agent_model_config agent_model_config_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.agent_model_config
    ADD CONSTRAINT agent_model_config_pkey PRIMARY KEY (id);


--
-- Name: data_collection data_collection_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.data_collection
    ADD CONSTRAINT data_collection_pkey PRIMARY KEY (id);


--
-- Name: mtd_access mtd_access_entity_id_entity_type_user_id_key; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_access
    ADD CONSTRAINT mtd_access_entity_id_entity_type_user_id_key UNIQUE (entity_id, entity_type, user_id);


--
-- Name: mtd_access mtd_access_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_access
    ADD CONSTRAINT mtd_access_pkey PRIMARY KEY (id);


--
-- Name: mtd_dashboard mtd_dashboard_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_dashboard
    ADD CONSTRAINT mtd_dashboard_pkey PRIMARY KEY (id);


--
-- Name: mtd_file mtd_file_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_file
    ADD CONSTRAINT mtd_file_pkey PRIMARY KEY (id);


--
-- Name: mtd_folder mtd_folder_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_folder
    ADD CONSTRAINT mtd_folder_pkey PRIMARY KEY (id);


--
-- Name: mtd_project mtd_project_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_project
    ADD CONSTRAINT mtd_project_pkey PRIMARY KEY (id);


--
-- Name: mtd_results mtd_results_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_results
    ADD CONSTRAINT mtd_results_pkey PRIMARY KEY (id);


--
-- Name: mtd_session_artifact mtd_session_artifact_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session_artifact
    ADD CONSTRAINT mtd_session_artifact_pkey PRIMARY KEY (id);


--
-- Name: mtd_session mtd_session_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session
    ADD CONSTRAINT mtd_session_pkey PRIMARY KEY (id);


--
-- Name: mtd_session_workspace mtd_session_workspace_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session_workspace
    ADD CONSTRAINT mtd_session_workspace_pkey PRIMARY KEY (session_id);


--
-- Name: mtd_table mtd_table_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_table
    ADD CONSTRAINT mtd_table_pkey PRIMARY KEY (id);


--
-- Name: mtd_user_invitations mtd_user_invitations_invite_token_key; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_user_invitations
    ADD CONSTRAINT mtd_user_invitations_invite_token_key UNIQUE (invite_token);


--
-- Name: mtd_user_invitations mtd_user_invitations_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_user_invitations
    ADD CONSTRAINT mtd_user_invitations_pkey PRIMARY KEY (id);


--
-- Name: mtd_users mtd_users_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_users
    ADD CONSTRAINT mtd_users_pkey PRIMARY KEY (id);


--
-- Name: mtd_variant_analysis_cache mtd_variant_analysis_cache_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_variant_analysis_cache
    ADD CONSTRAINT mtd_variant_analysis_cache_pkey PRIMARY KEY (table_name);


--
-- Name: upload_locks upload_locks_pkey; Type: CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.upload_locks
    ADD CONSTRAINT upload_locks_pkey PRIMARY KEY (folder_id);


--
-- Name: idx_chart_type; Type: INDEX; Schema: charts_storage; Owner: -
--

CREATE INDEX idx_chart_type ON charts_storage.chart_storage USING btree (chart_type);


--
-- Name: idx_created_at; Type: INDEX; Schema: charts_storage; Owner: -
--

CREATE INDEX idx_created_at ON charts_storage.chart_storage USING btree (created_at);


--
-- Name: idx_query_hash; Type: INDEX; Schema: charts_storage; Owner: -
--

CREATE INDEX idx_query_hash ON charts_storage.chart_storage USING btree (query_hash);


--
-- Name: idx_audit_logs_action_type; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_audit_logs_action_type ON instance01.admin_audit_logs USING btree (action_type);


--
-- Name: idx_audit_logs_actor; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_audit_logs_actor ON instance01.admin_audit_logs USING btree (actor_id);


--
-- Name: idx_audit_logs_timestamp; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_audit_logs_timestamp ON instance01.admin_audit_logs USING btree ("timestamp");


--
-- Name: idx_invite_email; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_invite_email ON instance01.mtd_user_invitations USING btree (email);


--
-- Name: idx_invite_status; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_invite_status ON instance01.mtd_user_invitations USING btree (status);


--
-- Name: idx_invite_token; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_invite_token ON instance01.mtd_user_invitations USING btree (invite_token);


--
-- Name: idx_session_artifact_session_type; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_session_artifact_session_type ON instance01.mtd_session_artifact USING btree (session_id, artifact_type, created_at);


--
-- Name: idx_session_workspace_folder; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX idx_session_workspace_folder ON instance01.mtd_session_workspace USING btree (folder_id);


--
-- Name: mt_file_uploaded_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mt_file_uploaded_by_idx ON instance01.mtd_file USING btree (uploaded_by);


--
-- Name: mtd_access_granted_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_access_granted_by_idx ON instance01.mtd_access USING btree (granted_by);


--
-- Name: mtd_access_user_id_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_access_user_id_idx ON instance01.mtd_access USING btree (user_id);


--
-- Name: mtd_dashboard_created_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_dashboard_created_by_idx ON instance01.mtd_dashboard USING btree (created_by);


--
-- Name: mtd_dashboard_parent_folder_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_dashboard_parent_folder_idx ON instance01.mtd_dashboard USING btree (parent_folder_id);


--
-- Name: mtd_file_parent_folder_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_file_parent_folder_idx ON instance01.mtd_file USING btree (parent_folder_id);


--
-- Name: mtd_folder_created_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_folder_created_by_idx ON instance01.mtd_folder USING btree (created_by);


--
-- Name: mtd_folder_project_id_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_folder_project_id_idx ON instance01.mtd_folder USING btree (project_id);


--
-- Name: mtd_project_created_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_project_created_by_idx ON instance01.mtd_project USING btree (created_by);


--
-- Name: mtd_results_session_id; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_results_session_id ON instance01.mtd_results USING btree (session_id);


--
-- Name: mtd_results_table_id_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_results_table_id_idx ON instance01.mtd_results USING btree (table_id);


--
-- Name: mtd_session_created_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_session_created_by_idx ON instance01.mtd_session USING btree (created_by);


--
-- Name: mtd_session_folder_id_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_session_folder_id_idx ON instance01.mtd_session USING btree (folder_id);


--
-- Name: mtd_table_created_by_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_table_created_by_idx ON instance01.mtd_table USING btree (created_by);


--
-- Name: mtd_table_file_id_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_table_file_id_idx ON instance01.mtd_table USING btree (parent_id);


--
-- Name: mtd_users_email_idx; Type: INDEX; Schema: instance01; Owner: -
--

CREATE INDEX mtd_users_email_idx ON instance01.mtd_users USING btree (email);


--
-- Name: mtd_user_invitations fk_invited_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_user_invitations
    ADD CONSTRAINT fk_invited_by FOREIGN KEY (invited_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_file mt_file_uploaded_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_file
    ADD CONSTRAINT mt_file_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_access mtd_access_granted_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_access
    ADD CONSTRAINT mtd_access_granted_by FOREIGN KEY (granted_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_access mtd_access_user_id; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_access
    ADD CONSTRAINT mtd_access_user_id FOREIGN KEY (user_id) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_dashboard mtd_dashboard_created_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_dashboard
    ADD CONSTRAINT mtd_dashboard_created_by FOREIGN KEY (created_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_dashboard mtd_dashboard_parent_folder; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_dashboard
    ADD CONSTRAINT mtd_dashboard_parent_folder FOREIGN KEY (parent_folder_id) REFERENCES instance01.mtd_folder(id);


--
-- Name: mtd_file mtd_file_parent_folder; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_file
    ADD CONSTRAINT mtd_file_parent_folder FOREIGN KEY (parent_folder_id) REFERENCES instance01.mtd_folder(id);


--
-- Name: mtd_folder mtd_folder_created_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_folder
    ADD CONSTRAINT mtd_folder_created_by FOREIGN KEY (created_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_folder mtd_folder_project_id; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_folder
    ADD CONSTRAINT mtd_folder_project_id FOREIGN KEY (project_id) REFERENCES instance01.mtd_project(id);


--
-- Name: mtd_project mtd_project_created_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_project
    ADD CONSTRAINT mtd_project_created_by FOREIGN KEY (created_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_results mtd_results_table_id; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_results
    ADD CONSTRAINT mtd_results_table_id FOREIGN KEY (table_id) REFERENCES instance01.mtd_table(id);


--
-- Name: mtd_session_artifact mtd_session_artifact_folder_id_fkey; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session_artifact
    ADD CONSTRAINT mtd_session_artifact_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES instance01.mtd_folder(id) ON DELETE CASCADE;


--
-- Name: mtd_session_artifact mtd_session_artifact_session_id_fkey; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session_artifact
    ADD CONSTRAINT mtd_session_artifact_session_id_fkey FOREIGN KEY (session_id) REFERENCES instance01.mtd_session(id) ON DELETE CASCADE;


--
-- Name: mtd_session mtd_session_created_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session
    ADD CONSTRAINT mtd_session_created_by FOREIGN KEY (created_by) REFERENCES instance01.mtd_users(id);


--
-- Name: mtd_session mtd_session_folder_id; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session
    ADD CONSTRAINT mtd_session_folder_id FOREIGN KEY (folder_id) REFERENCES instance01.mtd_folder(id);


--
-- Name: mtd_session_workspace mtd_session_workspace_folder_id_fkey; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session_workspace
    ADD CONSTRAINT mtd_session_workspace_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES instance01.mtd_folder(id) ON DELETE CASCADE;


--
-- Name: mtd_session_workspace mtd_session_workspace_session_id_fkey; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_session_workspace
    ADD CONSTRAINT mtd_session_workspace_session_id_fkey FOREIGN KEY (session_id) REFERENCES instance01.mtd_session(id) ON DELETE CASCADE;


--
-- Name: mtd_table mtd_table_created_by; Type: FK CONSTRAINT; Schema: instance01; Owner: -
--

ALTER TABLE ONLY instance01.mtd_table
    ADD CONSTRAINT mtd_table_created_by FOREIGN KEY (created_by) REFERENCES instance01.mtd_users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict PfA4WKwRZgOid20uuubR095AvNMwvU1I1ITANCwyEoVNCkwG9EJhaIJz5f8059O

