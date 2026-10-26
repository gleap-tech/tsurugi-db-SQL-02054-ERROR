drop table if exists chk01_strings_source;
drop table if exists chk01_strings_result;

create table chk01_strings_source (
  id int not null,
  name_a varchar(*) not null,
  name_b varchar(*) not null,
  primary key (id)
);

create table chk01_strings_result (
  id int generated always as identity,
  via varchar(*) not null,
  name_a varchar(*) not null,
  name_b varchar(*) not null,
  primary key (id)
);
