import snowflake from 'snowflake-sdk';

let connection: snowflake.Connection | null = null;

export async function getSnowflakeConnection(): Promise<snowflake.Connection> {
  if (connection) return connection;

  return new Promise((resolve, reject) => {
    const conn = snowflake.createConnection({
      account: process.env.SNOWFLAKE_ACCOUNT!,
      username: process.env.SNOWFLAKE_USER!,
      password: process.env.SNOWFLAKE_PASSWORD!,
      warehouse: process.env.SNOWFLAKE_WAREHOUSE || 'COMPUTE_WH',
      database: process.env.SNOWFLAKE_DATABASE || 'DBAPI_REPLICA_DB',
      role: process.env.SNOWFLAKE_ROLE || 'ACCOUNTADMIN',
    });

    conn.connect((err, conn) => {
      if (err) {
        console.error('Snowflake connection error:', err);
        reject(err);
      } else {
        connection = conn;
        resolve(conn);
      }
    });
  });
}

export async function executeQuery<T = Record<string, unknown>>(sql: string): Promise<T[]> {
  const conn = await getSnowflakeConnection();
  
  return new Promise((resolve, reject) => {
    conn.execute({
      sqlText: sql,
      complete: (err, stmt, rows) => {
        if (err) {
          console.error('Query error:', err);
          reject(err);
        } else {
          resolve((rows || []) as T[]);
        }
      }
    });
  });
}
