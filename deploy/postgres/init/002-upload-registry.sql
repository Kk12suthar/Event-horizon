CREATE SCHEMA IF NOT EXISTS uploads;
--
-- PostgreSQL database dump
--

\restrict 91TbJTm9eIXTGuOcnfx2EiXod1Zy2VeFe0xIzRHlpueylzLvDeJ3bcNCpOIO8Pt

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _upload_completed_trigger; Type: TABLE; Schema: uploads; Owner: -
--

CREATE TABLE uploads._upload_completed_trigger (
    id integer NOT NULL,
    table_name character varying(255) NOT NULL,
    triggered_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: _upload_completed_trigger_id_seq; Type: SEQUENCE; Schema: uploads; Owner: -
--

CREATE SEQUENCE uploads._upload_completed_trigger_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: _upload_completed_trigger_id_seq; Type: SEQUENCE OWNED BY; Schema: uploads; Owner: -
--

ALTER SEQUENCE uploads._upload_completed_trigger_id_seq OWNED BY uploads._upload_completed_trigger.id;


--
-- Name: table_registry; Type: TABLE; Schema: uploads; Owner: -
--

CREATE TABLE uploads.table_registry (
    table_name text NOT NULL,
    table_type text NOT NULL,
    session_id text,
    folder_id text,
    created_at timestamp without time zone DEFAULT now(),
    created_by text,
    is_protected boolean DEFAULT true,
    metadata jsonb DEFAULT '{}'::jsonb,
    friendly_name text
);


--
-- Name: _upload_completed_trigger id; Type: DEFAULT; Schema: uploads; Owner: -
--

ALTER TABLE ONLY uploads._upload_completed_trigger ALTER COLUMN id SET DEFAULT nextval('uploads._upload_completed_trigger_id_seq'::regclass);


--
-- Name: _upload_completed_trigger _upload_completed_trigger_pkey; Type: CONSTRAINT; Schema: uploads; Owner: -
--

ALTER TABLE ONLY uploads._upload_completed_trigger
    ADD CONSTRAINT _upload_completed_trigger_pkey PRIMARY KEY (id);


--
-- Name: table_registry table_registry_pkey; Type: CONSTRAINT; Schema: uploads; Owner: -
--

ALTER TABLE ONLY uploads.table_registry
    ADD CONSTRAINT table_registry_pkey PRIMARY KEY (table_name);


--
-- Name: idx_registry_folder; Type: INDEX; Schema: uploads; Owner: -
--

CREATE INDEX idx_registry_folder ON uploads.table_registry USING btree (folder_id);


--
-- Name: idx_registry_protected; Type: INDEX; Schema: uploads; Owner: -
--

CREATE INDEX idx_registry_protected ON uploads.table_registry USING btree (is_protected);


--
-- Name: idx_registry_session; Type: INDEX; Schema: uploads; Owner: -
--

CREATE INDEX idx_registry_session ON uploads.table_registry USING btree (session_id);


--
-- PostgreSQL database dump complete
--

\unrestrict 91TbJTm9eIXTGuOcnfx2EiXod1Zy2VeFe0xIzRHlpueylzLvDeJ3bcNCpOIO8Pt

