import numpy as np
import pandas as pd
from tspdb.src.database_module.db_class import Interface
#######################TO DO##########################
#1 get SUV instead of all getU,getS, getV
######################################################
class plpyimp(Interface):
    
    def __init__(self, engine):
            self.engine = engine

            pass

    def get_time_series(self, name, start, end = None, start_ts = '1970/01/01 00:00:00', value_column="ts", index_column='row_id', Desc=False, interval = 60, aggregation_method = 'average' ):

        """
        query time series table to return equally-spaced time series values from a certain range  [start to end]
        or all values with time stamp/index greater than start  (if end is None)
        ----------
        Parameters
        ----------
        name: string 
            table (time series) name in database

        start: int or  timestamp
            start index (timestamp) of the range query

        end: int, timestamp 
            last index (timestamp) of the range query

        value_column: string
            name of column than contain time series value

        index_column: string  
            name of column that contains time series index/timestamp

        interval: float optional (default=60) 
            if time-index type is timestamp, determine the period (in seconds) in which the timestamps are truncated  

        aggregation_method: str optional (default='average') 
            the method used to aggragte values belonging to the same interval. options are: 'average', 'max', 'min', and 'median'  
        
        desc: boolean optional (default=false) 
            if true(false),  the returned values are sorted descendingly (ascendingly) according to index_column 
        ----------
        Returns
        ----------
        array, shape [(end - start +1) or  ceil(end(in seconds) - start(in seconds) +1) / interval ]
            Values of time series in the time interval start to end sorted according to index_col
        """
        # check if hypertable

        hypertable = self.engine.execute("SELECT count(*)>=1 as h FROM timescaledb_information.hypertable WHERE table_schema='public' AND table_name='%s';" % name)[0]['h']
            
        if isinstance(start, (int, np.integer)) and (isinstance(end, (int, np.integer)) or end is None):
            if end is None:
                sql = 'Select ' + value_column + " from  " + name + " where " + index_column + " >= "+str(start)+" order by "+index_column
                result = self.engine.execute(sql)

            else:
                if not Desc:
                    sql = 'Select ' + value_column + " from  " + name + " where " + index_column + " >= "+str(start)+" and " + index_column + " <= "+str(end)+" order by " + index_col
                else:
                    sql = 'Select ' + value_column + " from  " + name + " where " + index_column + " >= "+str(start)+" and " + index_column + " <= "+str(end)+" order by " + index_col + ' Desc'
                result = self.engine.execute(sql)
            result = [row for row in result]
            return [(row[value_column],) for row in result]

        elif  isinstance(start, (pd.Timestamp)) and (isinstance(end, (pd.Timestamp)) or end is None):
            #SELECT
            #time_bucket_gapfill('00:00:05', time) AS date,
            #avg(ts)
            #FROM ts_basic_ts_5_5
            #WHERE time >= '1/10/2012' AND time < ' 2012-10-06 18:53:15'
            #GROUP BY date
            #ORDER BY date;

            
            seconds = interval%60
            minutes = int(interval/60)
            hours = int(interval/3600)
            interval_str = '%s:%s:%s'%(hours, minutes, seconds)
            
            agg_func_dict = {'average': 'AVG', 'min': 'MIN', 'max': 'MAX'}
            try:
                agg_function = agg_func_dict[aggregation_method]
            except KeyError as e:
                print ('aggregation_method not valid choose from ("average", "min", "max"), Exception: "%s"' % str(e))
                raise
            ## might be needed
            start_ts_str = start_ts.strftime('%Y-%m-%d %H:%M:%S')
            ## fix strings formatting
            if hypertable:
                if end is None:
                    sql = "SELECT time_bucket_gapfill('%s', "+index_column+") AS date, "+agg_function+"("+value_column+") as avg_val FROM "+name+" where "+index_column+" >= '%s' and  "+index_column+" <= '%s' GROUP BY date ORDER BY date"
                    sql = sql%(interval_str, start.strftime('%Y-%m-%d %H:%M:%S'), 'now()',)
                else:
                    sql = "SELECT time_bucket_gapfill('%s', "+index_column+") AS date, "+agg_function+"("+value_column+") as avg_val FROM "+name+" where "+index_column+" >= '%s' and  "+index_column+" <= '%s' GROUP BY date ORDER BY date"
                    sql = sql%(interval_str, start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S'),)
            else:
                if end is None:
                    select_sql = "select "+agg_function+"(m."+value_column+") avg_val from "+name+" m right join intervals f on m."+index_column+" >= f.start_time and m."+index_column+" < f.end_time where f.end_time > "+start_ts_str+"  group by f.start_time, f.end_time order by f.start_time"
                    generate_series_sql = "with intervals as (select n as start_time,n+'"+interval_str+"'::interval as end_time from generate_series('"+start.strftime('%Y-%m-%d %H:%M:%S')+"'::timestamp, now(),'"+interval_str+"'::interval) as n )"
                else:
                    generate_series_sql = "with intervals as (select n as start_time,n+'"+interval_str+"'::interval as end_time from generate_series('%s'::timestamp, '%s'::timestamp,'"+interval_str+"'::interval) as n )" 
                    generate_series_sql = generate_series_sql % (start_ts_str,end.strftime('%Y-%m-%d %H:%M:%S'),)
                    select_sql = "select "+agg_function+"(m."+value_column+") avg_val from "+name+" m right join intervals f on m."+index_column+" >= f.start_time and m."+index_column+" < f.end_time where f.end_time > '%s' and  f.start_time <= '%s' group by f.start_time, f.end_time order by f.start_time" 
                    select_sql = select_sql%(start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S'),)
                
                
                sql = generate_series_sql+ select_sql
            if Desc: sql += 'DESC'
            result = self.engine.execute(sql)
            result = [row for row in result]
            return [(row['avg_val'],) for row in result]

        else:
             raise Exception('start and end values must either be integers or pd.timestamp')

    def get_U_row(self, table_name, tsrow_range, models_range,k, return_modelno = False):

        """
        query the U matrix from the database table '... U_table' created via the prediction index. the query depend on the ts_row
        range [tsrow_range[0] to tsrow_range[1]] and model range [models_range[0] to models_range[1]] (both inclusive)
        ----------
        Parameters
        ----------
        table_name: string
            table name in database
        
        tsrow_range:list of length 2 
            start and end index  of the range query predicate on ts_row
        
        models_range:list of length 2 
            start and end index  of the range query predicate on model_no

        k: int
            number of singular values retained in the prediction index

        return_modelno: boolean optional (default=false) 
            if true,  submodel numbers are returned in the first column   
        ----------
        Returns
        ---------- 
        array 
        queried values for the selected range
        """
        columns = 'u'+ ',u'.join([str(i) for i in range(1, k + 1)])
        if return_modelno :
            columns = 'modelno,'+ columns
        query = "SELECT "+ columns +" FROM " + table_name + " WHERE tsrow >= %s and tsrow <= %s and (modelno >= %s and modelno <= %s) order by row_id; "
        query = query %(tsrow_range[0], tsrow_range[1], models_range[0], models_range[1])
        result = self.engine.execute(query)
        columns = columns.split(',')
        result = [[row[ci] for ci in columns] for row in result]
        #return pd.DataFrame(result).values
        return np.array(result)

    def get_V_row(self, table_name, tscol_range,k, models_range = [0,10**10] ,return_modelno = False):


        """
        query the V matrix from the database table '... V_table' created via the index. the query depend on the ts_col
        range [tscol_range[0] to tscol_range[1]]  (inclusive)
        ----------
        Parameters
        ----------
        table_name: string
            table name in database
        
        tscol_range:list of length 2 
            start and end index  of the range query predicate on ts_col
        k: int
            number of singular values retained in the prediction index

        return_modelno: boolean optional (default=false) 
            if true,  submodel numbers are returned in the first column   
        ----------
        Returns
        ---------- 
        array 
        queried values for the selected range
        """
        
        
        columns = 'v'+ ',v'.join([str(i) for i in range(1, k + 1)])
        if return_modelno :
            columns = 'modelno,'+ columns
        query = "SELECT " + columns + " FROM " + table_name + " WHERE tscolumn >= %s and tscolumn <= %s and (modelno >= %s and modelno <= %s)   order by row_id; "
        query = query %(tscol_range[0], tscol_range[1], models_range[0], models_range[1])

        # query = "SELECT " + columns + " FROM " + table_name + " WHERE tscolumn >= %s and tscolumn <= %s order by row_id; "
        # query = query %(tscol_range[0], tscol_range[1])
        result = self.engine.execute(query)
        # result = [row for row in result]
        columns = columns.split(',')
        result = [[row[ci] for ci in columns] for row in result]
        #return pd.DataFrame(result).values
        return np.array(result)



    def get_S_row(self, table_name, models_range, k ,return_modelno = False):

        """
        query the S matrix from the database table '... s_table' created via the index. the query depend on the model
        range [models_range[0] to models_range[1]] ( inclusive)
        ----------
        Parameters
        ----------
        table_name: string
            table name in database
        
        models_range: list of length 2 
            start and end index  of the range query predicate on model_no
        
        k: int
            number of singular values retained in the prediction index

        return_modelno: boolean optional (default=false) 
            if true,  submodel numbers are returned in the first column   
        ----------
        Returns
        ---------- 
        array 
        queried values for the selected range
        """
        columns = 's'+ ',s'.join([str(i) for i in range(1, k + 1)])
        if return_modelno :
            columns = 'modelno,'+ columns
        # if models_range is None:
        #     query = "SELECT "+ columns +" FROM " + table_name + " WHERE tscolumn >= %s and tscolumn <= %s ; "
        query = "SELECT "+ columns +" FROM " + table_name + " WHERE modelno >= %s and modelno <= %s order by modelno;"
        query = query %(models_range[0], models_range[1])
        result = self.engine.execute(query)
        columns = columns.split(',')        
        result = [[row[ci] for ci in columns] for row in result]
        #return pd.DataFrame(result).values
        return np.array(result)


    def get_SUV(self, table_name, tscol_range, tsrow_range, models_range, k ,return_modelno = False):

        """
        query the S, U, V matric from the database tables created via the prediction index. the query depend on the model
        range, ts_col range, and ts_row range (inclusive ranges)
            
        ----------
        Parameters
        ----------
        table_name: string
            table name in database
        
        tscol_range:list of length 2 
            start and end index  of the range query predicate on ts_col
        
        tsrow_range:list of length 2 
            start and end index  of the range query predicate on ts_row
        
        models_range: list of length 2 
            start and end index  of the range query predicate on model_no
        
        k: int
            number of singular values retained in the prediction index

        return_modelno: boolean optional (default=false) 
            if true,  submodel numbers are returned in the first column   
        ----------
        Returns
        ---------- 
        S array 
        queried values for the selected range of S table

        U array 
        queried values for the selected range of U table

        V array 
        queried values for the selected range of V table

        """
        if return_modelno:
            model_no_str = 'modelno,'
        else:
            model_no_str = ''

        
        columns = model_no_str+'s'+ ',s'.join([str(i) for i in range(1, k + 1)])
        query = "SELECT "+ columns +" FROM " + table_name + "_s WHERE modelno = %s or modelno = %s order by modelno;"
        query = query %(models_range[0], models_range[1])
        result = self.engine.execute(query)
        columns = columns.split(',')
        S = [[row[ci] for ci in columns] for row in result]
        # result = [row for row in result]
        # S = pd.DataFrame(result).values

        columns = model_no_str+'v'+ ',v'.join([str(i) for i in range(1, k + 1)])
        query = "SELECT " + columns + " FROM " + table_name + "_v WHERE tscolumn = %s order by row_id; "
        query = query %(tscol_range[0])
        result = self.engine.execute(query)
        columns = columns.split(',')
        V = [[row[ci] for ci in columns] for row in result]
        
        # result = [row for row in result]
        # V = pd.DataFrame(result).values

        columns = model_no_str+'u'+ ',u'.join([str(i) for i in range(1, k + 1)])
        query = "SELECT "+ columns +" FROM " + table_name + "_u WHERE tsrow =  %s and (modelno = %s or modelno = %s) order by row_id; "
        query = query %(tsrow_range[0], models_range[0], models_range[1])
        result = self.engine.execute(query)
        columns = columns.split(',')
        U = [[row[ci] for ci in columns] for row in result]
        
        U,S,V = map(np.array, [U,S,V])
        # result = [row for row in result]
        # U = pd.DataFrame(result).values

        return U,S,V
    
    
    def create_table(self, table_name, df, primary_key=None, load_data=True,replace_if_exists = True , include_index=True,
                     index_label="row_id"):

        """
        Create table in the database with the same columns as the given pandas dataframe. Rows in the df will be written to
        the newly created table if load_data.
        ----------
        Parameters
        ----------
        table_name: string
            name of the table to be created
        
        df: Pandas dataframe
             Dataframe used to determine the schema of the table, as well as the data to be written in the new table (if load_data)
        
        primary_key: str, optional (default None)
            primary key of the table, should be one of the columns od the df
        
        load_data: boolean optioanl (default True) 
            if true, load data in df to the newly created table via bulk_inset()

        replace_if_exists: boolean optioanl (default False) 
            if true, drop the existing table of the same name (if exists).

        include_index: boolean optioanl (default True)
            if true, include the index column of the df, with its name being index_column_name
        
        index_label: string optional (default "index")
            name of the index column of the df in the newly created database table 

        """
        # drop table if exists:
        
        if replace_if_exists:
             self.drop_table(table_name)

        elif self.table_exists(table_name):
            raise ValueError('table with %s already exists in the database!' % table_name)
        # # create table in database

        types_dict = {'bool': 'boolean', 'object' : 'text','int64': 'bigint','int32': 'bigint','int32': 'bigint', 'float64': 'double precision', 'float32': 'double precision','float': 'double precision', 'datetime64[ns]':'TIMESTAMP' }
        columns = list(df.columns)
        col_dtypes = list(df.dtypes.values)
        if include_index:
            columns = [index_label] + columns
            col_dtypes = [df.index.dtype] + col_dtypes

        cols  = ['"'+a+'"   '+b for a,b in zip(columns, [types_dict[str(i)] for i in col_dtypes])]
        sql = ", \n".join(cols)

        self.engine.execute('create table '+table_name+' (' + sql + ');')
        
        query = "ALTER TABLE  %s ADD PRIMARY KEY (%s);" % (table_name, primary_key)
        if primary_key is not None:
            self.engine.execute(query)
        
        # load content
        if load_data:
            self.bulk_insert( table_name, df, include_index=include_index, index_label=index_label)




    def get_coeff(self, table_name, column = 'average'):

        """
        query the LR coefficients from the database materialized view  created via the index. 
        the query need to determine the queried column
            
        ----------
        Parameters
        ----------
        table_name: string
            table name in database
        
        column: string optioanl (default = 'average' )
            column name, for possible options, refer to ... 
        
        ----------
        Returns
        ---------- 
        coeffs array 
            queried coefficients for the selected average
        """
                
        query = "SELECT %s from %s order by %s" %(column , table_name, 'coeffpos')
        result = self.engine.execute(query)
        result = [row[column] for row in result]
        return np.array(result)

        # return result
    def drop_table(self, table_name):
        """
        Drop table from  database
        ----------
        Parameters
        ----------
        table_name: string
            name of the table to be deleted
        """

        query = " DROP TABLE IF EXISTS " +table_name + " Cascade; "

        self.engine.execute(query)
       
    def create_index(self, table_name, column, index_name='', ):
        """
        Constructs an index on a specified column of the specified table
        ----------
        Parameters
        ----------
        table_name: string 
            the name of the table to be indexed
        
        column: string 
            the name of the column to be indexed on
        
        index_name: string optional (Default '' (DB default))  
            the name of the index
        """
        query = 'CREATE INDEX %s ON %s (%s);' % (index_name  ,table_name,column)
        self.engine.execute(query)
      
    
    def create_coefficients_average_table(self, table_name, created_table_name, average_windows,max_model , refresh = False):
        """
        Create the matrilized view where the coefficient averages are calculated. 
        ----------
        Parameters
        ----------
        table_name:  string 
            the name of the coefficient tables

        created_table_name:  string 
            the name of the created matrilized view
        
        average_windows:  list 
            windows for averages to be calculated (e.g.: [10,20] calc. last ten and 20 models)
        
        max_model:  int 
            index of the latest submodel

        :param average_windows:  (list) windows for averages to be calculated (e.g.: [10,20] calc. last ten and 20 models)
        
        """
        if refresh:
            self.engine.execute('REFRESH MATERIALIZED VIEW '+ created_table_name)
            return
        s1 =  'SELECT coeffpos, avg(coeffvalue) as average,'
        s_a =  'avg(coeffvalue) FILTER (WHERE modelno <= %s and modelno > %s ) as Last%s'
        predicates = (',').join([s_a %(max_model,max_model-i,i) for i in average_windows])
        query = s1+ predicates + ' FROM %s group by coeffpos' %table_name
        self.create_table_from_query(created_table_name, query)
      

    def create_table_from_query(self, table_name, query, ):
        """
        Create a new table using the output of a certain query. This is equivalent to a materialized view in
        PostgreSQL and Oracle
        ----------
        Parameters
        ----------
        table_name:  string 
            the name of the table to be indexed
        query: string 
            query to create table from
        """
        query = 'CREATE MATERIALIZED VIEW %s AS ' %table_name + query
        self.engine.execute( query)
        
    def execute_query(self, query):
        """
        function that simply passes queries to DB
        ----------
        Parameters
        ----------
        query: string
            query to be executed
        ----------
        Returns
        ----------
        list
            query output
        """
        
        self.engine.execute(query)


    def insert(self, table_name, row, columns = None):
        """
        Insert a new full row in table_name
        ----------
        Parameters
        ----------
        table_name:  string 
            name of an existing table to insert the new row to
        row: list
            data to be inserted
        """

        row = ["'"+str(i)+"'" if (type(i) is str or type(i) == pd.Timestamp) else i for i in row ]
        row = [str(i) for i in row]
        if columns is not None: columns = '('+','.join(columns)+')'
        else: columns = ''
        query = 'insert into '+table_name+ columns+ ' values (' + ','.join(row)+');'
        self.engine.execute( query)
    
    def bulk_insert(self, table_name, df, include_index=True, index_label='row_id'):
        """
        Insert rows in pandas dataframe to table_name
        ----------
        Parameters
        ----------
        table_name: string 
            name of the table to which we will insert data
        
        df pandas dataframe 
            Dataframe containing the data to be added
        """
        
        # if include_index:
        #     data = np.concatenate((df.index.values.reshape(-1,1), df.values),1)
        # else:
        #     data = df.values

        # values = ','.join([str(tuple(i)) for i in data])
        # self.engine.execute('insert into '+ table_name+ ' values '+values + ';')

        df.to_csv('temp.csv', sep='\t', header=False, index=include_index, index_label=index_label)
        self.engine.execute('copy  '+ table_name+ " from 'temp.csv' WITH NULL AS '' ;")
        # os.remove("temp.csv")
    
    def table_exists(self, table_name, schema='public'):
        """
        check if a table exists in a certain database and schema
        ----------
        Parameters
        ----------
        table_name: string 
            name of the table
        
        schema: string default ('public')

        """
        sql = "SELECT EXISTS(SELECT *  FROM information_schema.tables WHERE table_name ='%s' AND table_schema = '%s' );" %(table_name,schema)
        return self.engine.execute(sql)[0]['exists']
    
    def query_table(self, table_name, columns_queried = [],predicate= '' ):
        """
        query columns from table_name according to a predicate
            
        ----------
        Parameters
        ----------
        table_name: string
            table name in database
        
        columns_queried: list of strings
            list of queries columns e.g. ['age', 'salary']
                    
        predicate: string optional (default = '')
            predicate written as string e.g.  'age < 1'
        ----------
        Returns
        ---------- 
        result array 
            queried tuples

        """
        columns = '"' + '","'.join(columns_queried) +'"'
        if predicate == '':
            query = "SELECT %s from %s ;" % (columns, table_name,)
            result =  self.engine.execute(query)
        else:
            query = "SELECT %s from %s where %s;" % (columns, table_name, predicate)
            result =  self.engine.execute(query)

        result = [[row[ci] for ci in columns_queried] for row in result]


        return result

    def delete(self, table_name, predicate):
        """
        check if a table exists in a certain database and schema
        ----------
        Parameters
        ----------
        table_name: string 
            name of the table contating the row to be deleted
        
        predicate: string
            the condition to determine deleted rows
        """

        if predicate == '': query = "DELETE from %s ;" % ( table_name)
        else: query = "DELETE from %s where %s;" % ( table_name, predicate)
        return self.engine.execute(query)

    def create_insert_trigger(self, table_name, index_name):
        
        function = '''CREATE or REPLACE FUNCTION %s_update_pindex_tg() RETURNS trigger  AS $$   plpy.execute("select update_pindex('%s');") $$LANGUAGE plpython3u;'''
        self.engine.execute(function %(index_name, index_name))
        query = "CREATE TRIGGER tspdb_update_pindex_tg AFTER insert ON " + table_name + " FOR EACH STATEMENT EXECUTE PROCEDURE " +index_name+"_update_pindex_tg(); "
        self.engine.execute(query)


    def drop_trigger(self, table_name):
        query = "DROP TRIGGER if EXISTS tspdb_update_pindex_tg on " + table_name 
        self.engine.execute(query)


    def get_extreme_value(self, table_name, column_name, extreme = 'min'):
        agg_func_dict = { 'min': 'MIN', 'max': 'MAX'}
        query = "SELECT " + extreme+"("+ column_name+") as ext from "+ table_name
        ext = self.engine.execute(query)[0]['ext']
        if isinstance(ext, (int, np.integer)): return ext
        else: return str(ext)
        