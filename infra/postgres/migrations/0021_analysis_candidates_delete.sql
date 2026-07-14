-- analysis worker replaces candidates with DELETE + INSERT; 0020 omitted DELETE.
GRANT SELECT, INSERT, UPDATE, DELETE ON analysis_candidates TO mirofish_app;
